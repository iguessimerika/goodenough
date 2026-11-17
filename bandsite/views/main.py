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
    members = db.list_members()
    duties = db.list_open_food_duties()
    brought = db.food_brought_counts()
    for m in members:
        m["owes"] = [d for d in duties if d["member_id"] == m["id"]]
        m["brought"] = brought.get(m["id"], 0)
    return render_template("members.html", members=members, food=duties)


def _soon(title, text):
    return render_template("soon.html", title=title, text=text)


@bp.get("/questionnaire")
@login_required
def questionnaire():
    return _soon("Questionnaire", "This area is still open. We'll fill it once you know what you want to ask.")
