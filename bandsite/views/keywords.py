from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from .. import db

bp = Blueprint("keywords", __name__, url_prefix="/keywords")


@bp.before_request
@login_required
def _require_login():
    pass


@bp.get("/")
def index():
    return render_template("keywords.html", keywords=db.list_keywords())


@bp.post("/new")
def new():
    name = request.form.get("name", "").strip()
    if not name or len(name) > 60:
        flash("Enter a name (60 characters at most).", "error")
    elif db.keyword_name_exists(name):
        flash(f"“{name}” already exists.", "error")
    else:
        db.create_keyword(name)
        flash(f"Keyword “{name}” created.", "ok")
    return redirect(url_for("keywords.index"))


@bp.post("/<int:keyword_id>/delete")
def delete(keyword_id):
    keyword = db.get_keyword(keyword_id) or abort(404)
    if keyword["is_fixed"]:
        flash(f"“{keyword['name']}” is needed by the song form and stays.", "error")
    else:
        db.delete_keyword(keyword_id)
        flash(f"“{keyword['name']}” deleted.", "ok")
    return redirect(url_for("keywords.index"))


@bp.post("/<int:keyword_id>/values")
def add_value(keyword_id):
    keyword = db.get_keyword(keyword_id) or abort(404)
    label = request.form.get("label", "").strip()
    if not label or len(label) > 60:
        flash("Enter a value (60 characters at most).", "error")
    elif db.value_exists(keyword_id, label):
        flash(f"“{label}” already exists under {keyword['name']}.", "error")
    else:
        db.add_keyword_value(keyword_id, label)
        flash(f"“{label}” added to {keyword['name']}.", "ok")
    return redirect(url_for("keywords.index") + f"#kw-{keyword_id}")


@bp.post("/values/<int:value_id>/delete")
def delete_value(value_id):
    value = db.get_keyword_value(value_id) or abort(404)
    db.delete_keyword_value(value_id)
    flash(f"“{value['label']}” deleted. Songs that used it now have no value.", "ok")
    return redirect(url_for("keywords.index") + f"#kw-{value['keyword_id']}")
