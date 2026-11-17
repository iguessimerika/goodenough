import hmac

import mysql.connector
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..user import Member, hash_password
from ..utils import is_safe_redirect

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("songs.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        row = db.get_member_by_email(email)
        member = Member(row) if row else None
        if member and member.check_password(password):
            login_user(member, remember=bool(request.form.get("remember")))
            target = request.args.get("next")
            return redirect(target if is_safe_redirect(target) else url_for("songs.index"))
        flash("Email or password is wrong.", "error")
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("songs.index"))
    band_code = current_app.config["BAND_CODE"]
    if not band_code:
        flash("Registration isn't enabled yet. Set the BAND_CODE variable.", "error")
        return redirect(url_for("auth.login"))

    instruments = db.list_values(db.INSTRUMENT)
    values = {"name": "", "email": "", "instrument_ids": []}
    if request.method == "POST":
        allowed = {i["id"] for i in instruments}
        chosen = [int(x) for x in request.form.getlist("instruments") if x.isdigit() and int(x) in allowed]
        values = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "instrument_ids": list(dict.fromkeys(chosen)),  # no duplicates, keeps the order
        }
        password = request.form.get("password", "")
        code = request.form.get("band_code", "").strip()
        errors = []
        if not hmac.compare_digest(code.encode(), band_code.encode()):
            errors.append("The band word is wrong.")
        if not values["name"] or len(values["name"]) > 80:
            errors.append("Enter a name (80 characters at most).")
        if "@" not in values["email"] or len(values["email"]) > 255:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("The password needs at least 8 characters.")
        if password != request.form.get("password2", ""):
            errors.append("The two passwords don't match.")
        if not errors and db.get_member_by_email(values["email"]):
            errors.append("There is already an account with this email address.")

        if not errors:
            try:
                member_id = db.create_member(
                    values["name"],
                    values["email"],
                    hash_password(password),
                    is_admin=db.count_members() == 0,  # the first member becomes admin
                    instrument_ids=values["instrument_ids"],
                )
            except mysql.connector.IntegrityError:
                errors.append("There is already an account with this email address.")
            else:
                member = Member(db.get_member(member_id))
                login_user(member)
                flash(f"Welcome to the band, {member.name}!", "ok")
                return redirect(url_for("songs.index"))
        for error in errors:
            flash(error, "error")
    return render_template("register.html", v=values, instruments=instruments)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You're signed out.", "ok")
    return redirect(url_for("main.landing"))
