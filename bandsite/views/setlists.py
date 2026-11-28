import json
import re
from datetime import date
from io import BytesIO

import mysql.connector
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from .. import db, pdf_notes

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
    setlist = db.get_setlist_with_sheets(setlist_id) or abort(404)
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


@bp.post("/setlists/<int:setlist_id>/pin")
def pin(setlist_id):
    setlist = db.get_setlist(setlist_id) or abort(404)
    if request.form.get("action") == "unpin":
        db.unpin_setlist(setlist_id)
        flash(f"“{setlist['name']}” is no longer pinned.", "ok")
    else:
        db.pin_setlist(setlist_id, current_user.id)
        flash(f"“{setlist['name']}” is pinned for the whole band.", "ok")
    if request.form.get("back") == "index":
        return redirect(url_for("setlists.index"))
    return _to_set_anchor(setlist_id)


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


# ---------------------------------------------------------------- sheet music in running order

def _sets_to_show(setlist, set_id):
    """One set if set_id is given, otherwise all sets of the setlist."""
    if set_id is None:
        return setlist["sets"]
    chosen = [one_set for one_set in setlist["sets"] if one_set["id"] == set_id]
    return chosen or abort(404)


def _parse_annotations(raw):
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        return {"pages": {}}
    return data


@bp.get("/setlists/<int:setlist_id>/sheets")
@bp.get("/setlists/<int:setlist_id>/sets/<int:set_id>/sheets")
def sheets(setlist_id, set_id=None):
    """All sheet-music PDFs of a set (or the whole setlist) one after another, with the band's notes."""
    setlist = db.get_setlist_with_sheets(setlist_id) or abort(404)
    sets = _sets_to_show(setlist, set_id)

    document_ids = [d["id"] for one_set in sets for entry in one_set["songs"] for d in entry["documents"]]
    annotations = db.get_annotations_for(document_ids)

    # Songs without a PDF stay in the plan, so the order on screen always matches the setlist.
    plan = []
    for one_set in sets:
        songs = []
        for number, entry in enumerate(one_set["songs"], start=1):
            songs.append({
                "number": number,
                "title": entry["title"],
                "artist": entry["artist"],
                "capo": entry["capo"],
                "singers": entry["singers"],
                "url": url_for("songs.detail", song_id=entry["song_id"]),
                "documents": [
                    {
                        "id": d["id"],
                        "filename": d["filename"],
                        "file": url_for("songs.document_file", document_id=d["id"]),
                        "editor": url_for("songs.document_editor", document_id=d["id"]),
                    }
                    for d in entry["documents"]
                ],
            })
        plan.append({"id": one_set["id"], "name": one_set["name"], "mood": one_set["mood"], "songs": songs})

    return render_template(
        "setlists/sheets.html",
        setlist=setlist,
        current_set=sets[0] if set_id is not None else None,
        plan=plan,
        document_count=len(document_ids),
        annotations_by_doc={str(i): _parse_annotations(annotations.get(i)) for i in document_ids},
    )


def _download_name(text):
    name = re.sub(r"[^\w\- ]+", "", text).strip().replace(" ", "-")
    return (name or "setlist")[:80] + ".pdf"


@bp.get("/setlists/<int:setlist_id>/sheets.pdf")
@bp.get("/setlists/<int:setlist_id>/sets/<int:set_id>/sheets.pdf")
def sheets_pdf(setlist_id, set_id=None):
    """All PDFs of a set (or the whole setlist) merged into one file, with a bookmark per song.

    For apps like forScore or a venue without internet. The band's notes are drawn into the pages;
    ?original=1 leaves them out.
    """
    from pypdf import PdfReader, PdfWriter

    setlist = db.get_setlist_with_sheets(setlist_id) or abort(404)
    sets = _sets_to_show(setlist, set_id)

    with_notes = request.args.get("original") != "1"
    document_ids = [d["id"] for one_set in sets for entry in one_set["songs"] for d in entry["documents"]]
    annotations = db.get_annotations_for(document_ids) if with_notes else {}

    writer = PdfWriter()
    skipped = []
    without_notes = []
    bookmarks = []  # (set name, [(song label, first page), …]); added once all pages exist
    for one_set in sets:
        song_marks = []
        for number, entry in enumerate(one_set["songs"], start=1):
            first_page = len(writer.pages)
            for d in entry["documents"]:
                file = db.get_document_file(d["id"])
                if file is None:
                    continue
                try:
                    reader = PdfReader(BytesIO(file["data"]))
                    if reader.is_encrypted:
                        reader.decrypt("")
                    start = len(writer.pages)
                    for page in reader.pages:
                        writer.add_page(page)
                except Exception:  # one broken or locked PDF must not break the whole download
                    skipped.append(d["filename"])
                    continue
                if pdf_notes.has_notes(annotations.get(d["id"])):
                    try:
                        pdf_notes.add_notes_to_pages(writer.pages[start:], annotations.get(d["id"]))
                    except Exception:  # the sheet is still useful without its notes
                        without_notes.append(d["filename"])
            if len(writer.pages) > first_page:
                song_marks.append((f"{number}. {entry['title']}", first_page))
        if song_marks:
            bookmarks.append((one_set["name"], song_marks))

    if len(writer.pages) == 0:
        flash("There is no sheet music in this set yet.", "error")
        return _to_set_anchor(setlist_id, set_id)

    for set_name, song_marks in bookmarks:
        parent = writer.add_outline_item(set_name, song_marks[0][1]) if len(sets) > 1 else None
        for label, page in song_marks:
            writer.add_outline_item(label, page, parent=parent)
    if skipped:
        flash("These PDFs couldn't be read and are missing from the download: " + ", ".join(skipped), "error")
    if without_notes:
        flash("The notes couldn't be added to: " + ", ".join(without_notes), "error")

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    name = setlist["name"] + (f" {sets[0]['name']}" if set_id is not None else "")
    response = send_file(output, mimetype="application/pdf", download_name=_download_name(name),
                         as_attachment=True, max_age=0)
    response.headers["Cache-Control"] = "private, no-cache"
    return response
