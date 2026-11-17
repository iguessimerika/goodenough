from datetime import date

import mysql.connector
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db

bp = Blueprint("setlists", __name__)


@bp.before_request
@login_required
def _require_login():
    pass


def _mood_choices():
    return db.list_values(db.MOOD)


def _pick_mood(raw, moods):
    if raw and raw.isdigit() and int(raw) in {m["id"] for m in moods}:
        return int(raw)
    return None


def _to_set_anchor(setlist_id, set_id=None):
    anchor = f"#set-{set_id}" if set_id else ""
    return redirect(url_for("setlists.detail", setlist_id=setlist_id) + anchor)


def _read_setlist_form(form):
    """Returns (values, errors)."""
    errors = []
    name = form.get("name", "").strip()
    information = form.get("information", "").strip()
    raw_date = form.get("event_date", "").strip()

    if not name:
        errors.append("Enter a name for the setlist.")
    elif len(name) > 120:
        errors.append("The name can have 120 characters at most.")
    if len(information) > 5000:
        errors.append("The information can have 5000 characters at most.")

    event_date = None
    if raw_date:
        try:
            event_date = date.fromisoformat(raw_date)
        except ValueError:
            errors.append("That date isn't valid.")

    return {"name": name, "event_date": event_date, "information": information}, errors


# ---------------------------------------------------------------- setlists

@bp.get("/setlists")
def index():
    return render_template("setlists/index.html", setlists=db.list_setlists())


@bp.route("/setlists/new", methods=["GET", "POST"])
def new():
    values = {"name": "", "event_date": None, "information": ""}
    if request.method == "POST":
        values, errors = _read_setlist_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            setlist_id = db.create_setlist(values["name"], values["event_date"], values["information"], current_user.id)
            flash("Setlist created. Add the first set below.", "ok")
            return _to_set_anchor(setlist_id)
    return render_template("setlists/form.html", setlist=None, v=values)


@bp.get("/setlists/<int:setlist_id>")
def detail(setlist_id):
    setlist = db.get_setlist(setlist_id) or abort(404)
    all_songs = db.list_song_choices()
    for one_set in setlist["sets"]:
        taken = {s["song_id"] for s in one_set["songs"]}
        one_set["available"] = [s for s in all_songs if s["id"] not in taken]
    return render_template(
        "setlists/detail.html",
        setlist=setlist,
        moods=_mood_choices(),
        next_set_name=f"Set {len(setlist['sets']) + 1}",
        has_songs=bool(all_songs),
    )


@bp.route("/setlists/<int:setlist_id>/edit", methods=["GET", "POST"])
def edit(setlist_id):
    setlist = db.get_setlist(setlist_id) or abort(404)
    values = {"name": setlist["name"], "event_date": setlist["event_date"], "information": setlist["information"] or ""}
    if request.method == "POST":
        values, errors = _read_setlist_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            db.update_setlist(setlist_id, values["name"], values["event_date"], values["information"])
            flash("Changes saved.", "ok")
            return _to_set_anchor(setlist_id)
    return render_template("setlists/form.html", setlist=setlist, v=values)


@bp.post("/setlists/<int:setlist_id>/delete")
def delete(setlist_id):
    setlist = db.get_setlist(setlist_id) or abort(404)
    db.delete_setlist(setlist_id)
    flash(f"“{setlist['name']}” deleted.", "ok")
    return redirect(url_for("setlists.index"))


# ---------------------------------------------------------------- sets

@bp.post("/setlists/<int:setlist_id>/sets")
def add_set(setlist_id):
    db.get_setlist(setlist_id) or abort(404)
    name = request.form.get("name", "").strip()
    if not name or len(name) > 80:
        flash("Enter a set name (80 characters at most).", "error")
        return _to_set_anchor(setlist_id)
    mood_id = _pick_mood(request.form.get("mood"), _mood_choices())
    set_id = db.create_set(setlist_id, name, mood_id)
    flash(f"“{name}” added.", "ok")
    return _to_set_anchor(setlist_id, set_id)


@bp.post("/sets/<int:set_id>/update")
def update_set(set_id):
    one_set = db.get_set(set_id) or abort(404)
    name = request.form.get("name", "").strip()
    if not name or len(name) > 80:
        flash("Enter a set name (80 characters at most).", "error")
    else:
        db.update_set(set_id, name, _pick_mood(request.form.get("mood"), _mood_choices()))
        flash("Set updated.", "ok")
    return _to_set_anchor(one_set["setlist_id"], set_id)


@bp.post("/sets/<int:set_id>/delete")
def delete_set(set_id):
    one_set = db.get_set(set_id) or abort(404)
    db.delete_set(set_id)
    flash(f"“{one_set['name']}” deleted.", "ok")
    return _to_set_anchor(one_set["setlist_id"])


@bp.post("/sets/<int:set_id>/move")
def move_set(set_id):
    one_set = db.get_set(set_id) or abort(404)
    db.move_set(set_id, request.form.get("direction", ""))
    return _to_set_anchor(one_set["setlist_id"], set_id)


# ---------------------------------------------------------------- songs in a set

@bp.post("/sets/<int:set_id>/songs")
def add_song(set_id):
    one_set = db.get_set(set_id) or abort(404)
    raw = request.form.get("song_id", "")
    if not raw.isdigit() or not db.song_exists(int(raw)):
        flash("Choose a song to add.", "error")
    else:
        try:
            db.add_song_to_set(set_id, int(raw))
        except mysql.connector.IntegrityError:
            flash("That song is already in this set.", "error")
    return _to_set_anchor(one_set["setlist_id"], set_id)


@bp.post("/set-songs/<int:set_song_id>/remove")
def remove_song(set_song_id):
    entry = db.get_set_song(set_song_id) or abort(404)
    db.remove_song_from_set(set_song_id)
    return _to_set_anchor(entry["setlist_id"], entry["set_id"])


@bp.post("/set-songs/<int:set_song_id>/move")
def move_song(set_song_id):
    entry = db.get_set_song(set_song_id) or abort(404)
    db.move_set_song(set_song_id, request.form.get("direction", ""))
    return _to_set_anchor(entry["setlist_id"], entry["set_id"])
