from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_required

from .. import db

bp = Blueprint("main", __name__)


@bp.get("/")
def landing():
    return render_template("landing.html")


@bp.get("/members")
@login_required
def members():
    return render_template("members.html", members=db.list_members())


def _soon(title, text):
    return render_template("soon.html", title=title, text=text)


@bp.get("/rehearsal")
@login_required
def rehearsal():
    return _soon("Rehearsal", "This is where you'll plan rehearsal dates and what you'll work on.")


@bp.get("/questionnaire")
@login_required
def questionnaire():
    return _soon("Questionnaire", "This area is still open. We'll fill it once you know what you want to ask.")
