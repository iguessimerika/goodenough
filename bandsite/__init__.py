import os

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from .band_info import BAND
from .extensions import csrf, login_manager


def create_app():
    load_dotenv()
    app = Flask(__name__)
    debug = os.environ.get("FLASK_DEBUG") == "1"

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        if not debug:
            raise RuntimeError("SECRET_KEY is not set.")
        secret = "local-development-only"

    app.config.update(
        SECRET_KEY=secret,
        BAND_CODE=os.environ.get("BAND_CODE", ""),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not debug,
        REMEMBER_COOKIE_SECURE=not debug,
        REMEMBER_COOKIE_HTTPONLY=True,
    )
    # Railway sits behind a proxy: take https and host from its headers.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in."

    from . import db, user  # noqa: F401  (user registers the login loader)
    from .views import auth, keywords, main, songs

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(songs.bp)
    app.register_blueprint(keywords.bp)

    @app.context_processor
    def inject_band():
        return {"band": BAND}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        # YouTube embeds need a referrer.
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        flash("The file is too large. The limit is 16 MB.", "error")
        return redirect(request.referrer or url_for("songs.index"))

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        flash("Your session expired. Please try again.", "error")
        return redirect(request.referrer or url_for("main.landing"))

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        app.logger.exception("Database error: %s", error)
        return render_template(
            "error.html",
            title="Database unavailable",
            text="The database can't be reached right now. Try again in a moment.",
        ), 503

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", title="Page not found", text="There is nothing at this address."), 404

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", title="No access", text="You don't have permission to do that."), 403

    return app
