import json
import re
from io import BytesIO

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from .. import db
from ..utils import clean_annotations, youtube_id

bp = Blueprint("songs", __name__)


@bp.before_request
@login_required
def _require_login():
    pass


def _options():
    return {
        "phases": db.list_values(db.PHASE),
        "moods": db.list_values(db.MOOD),
        "members": db.list_members(),
    }


def _pick_id(raw, allowed):
    if raw and raw.isdigit() and int(raw) in {item["id"] for item in allowed}:
        return int(raw)
    return None


def _with_video(song):
    song["youtube_id"] = youtube_id(song["youtube_url"])
    return song


def _read_form(form, options):
    """Reads and validates the song form. Returns (values, errors)."""
    errors = []
    title = form.get("title", "").strip()
    artist = form.get("artist", "").strip()
    information = form.get("information", "").strip()
    youtube_url = form.get("youtube_url", "").strip()

    if not title:
        errors.append("Enter a title.")
    if not artist:
        errors.append("Enter the artist.")
    if len(title) > 200 or len(artist) > 200:
        errors.append("Title and artist can have 200 characters at most.")
    if len(information) > 5000:
        errors.append("The information can have 5000 characters at most.")

    try:
        capo = int(form.get("capo") or 0)
    except ValueError:
        capo = 0
        errors.append("Capo must be a number.")
    if not 0 <= capo <= 12:
        errors.append("Capo goes from 0 (no capo) to 12.")

    if youtube_url:
        if len(youtube_url) > 500:
            errors.append("The YouTube link is too long.")
        elif not youtube_id(youtube_url):
            errors.append("I don't recognise that YouTube link. Copy the address from the address bar or use Share.")

    allowed_singers = {m["id"] for m in options["members"]}
    singer_ids = [int(x) for x in form.getlist("singers") if x.isdigit() and int(x) in allowed_singers]

    values = {
        "title": title,
        "artist": artist,
        "capo": capo,
        "information": information,
        "youtube_url": youtube_url,
        "phase_id": _pick_id(form.get("phase"), options["phases"]),
        "mood_id": _pick_id(form.get("mood"), options["moods"]),
        "singer_ids": singer_ids,
    }
    return values, errors


@bp.get("/songs")
def index():
    options = _options()
    search = request.args.get("q", "").strip()
    phase_id = request.args.get("phase", type=int)
    mood_id = request.args.get("mood", type=int)
    songs = [_with_video(s) for s in db.list_songs(search, phase_id, mood_id)]
    return render_template(
        "songs/index.html",
        songs=songs,
        q=search,
        phase_id=phase_id,
        mood_id=mood_id,
        filtered=bool(search or phase_id or mood_id),
        **options,
    )


@bp.route("/songs/new", methods=["GET", "POST"])
def new():
    options = _options()
    values = {
        "title": "", "artist": "", "capo": 0, "information": "", "youtube_url": "",
        "phase_id": None, "mood_id": None, "singer_ids": [],
    }
    if request.method == "POST":
        values, errors = _read_form(request.form, options)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            song_id = db.create_song(values, current_user.id)
            flash(f"“{values['title']}” is saved. You can upload sheet music now.", "ok")
            return redirect(url_for("songs.detail", song_id=song_id))
    return render_template("songs/form.html", song=None, v=values, **options)


@bp.get("/songs/<int:song_id>")
def detail(song_id):
    song = db.get_song(song_id) or abort(404)
    return render_template("songs/detail.html", song=_with_video(song))


@bp.route("/songs/<int:song_id>/edit", methods=["GET", "POST"])
def edit(song_id):
    song = db.get_song(song_id) or abort(404)
    options = _options()
    values = {
        "title": song["title"], "artist": song["artist"], "capo": song["capo"],
        "information": song["information"] or "", "youtube_url": song["youtube_url"] or "",
        "phase_id": song["phase_id"], "mood_id": song["mood_id"],
        "singer_ids": [s["id"] for s in song["singers"]],
    }
    if request.method == "POST":
        values, errors = _read_form(request.form, options)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            db.update_song(song_id, values)
            flash("Changes saved.", "ok")
            return redirect(url_for("songs.detail", song_id=song_id))
    return render_template("songs/form.html", song=song, v=values, **options)


@bp.post("/songs/<int:song_id>/delete")
def delete(song_id):
    song = db.get_song(song_id) or abort(404)
    db.delete_song(song_id)
    flash(f"“{song['title']}” deleted.", "ok")
    return redirect(url_for("songs.index"))


# ---------------------------------------------------------------- sheet music (PDF)

def _clean_filename(raw):
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:200]


@bp.post("/songs/<int:song_id>/documents")
def upload_document(song_id):
    song = db.get_song(song_id) or abort(404)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a PDF file first.", "error")
        return redirect(url_for("songs.detail", song_id=song_id))

    filename = _clean_filename(upload.filename)
    data = upload.read()
    if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        flash("That isn't a PDF file. For practising and annotating, only PDF works for now.", "error")
    elif len(data) == 0:
        flash("The file is empty.", "error")
    else:
        db.create_document(song["id"], filename, data, current_user.id)
        flash(f"“{filename}” uploaded.", "ok")
    return redirect(url_for("songs.detail", song_id=song_id))


@bp.get("/documents/<int:document_id>/file")
def document_file(document_id):
    document = db.get_document_file(document_id) or abort(404)
    response = send_file(
        BytesIO(document["data"]),
        mimetype="application/pdf",
        download_name=document["filename"],
        as_attachment=request.args.get("download") == "1",
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@bp.get("/documents/<int:document_id>/editor")
def document_editor(document_id):
    document = db.get_document(document_id) or abort(404)
    stored = db.get_annotations(document_id) or abort(404)
    try:
        annotations = json.loads(stored["annotations"]) if stored["annotations"] else {"pages": {}}
    except ValueError:
        annotations = {"pages": {}}
    return render_template(
        "songs/editor.html",
        document=document,
        annotations=annotations,
        version=stored["annotation_version"],
    )


@bp.post("/documents/<int:document_id>/annotations")
def document_annotations(document_id):
    db.get_document(document_id) or abort(404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invalid data."), 400
    try:
        version = int(payload.get("version"))
    except (TypeError, ValueError):
        return jsonify(error="Invalid version."), 400
    cleaned = clean_annotations(payload.get("annotations"))
    if cleaned is None:
        return jsonify(error="The notes are invalid or too large."), 400
    if not db.save_annotations(document_id, cleaned, version):
        return jsonify(error="conflict"), 409
    return jsonify(version=version + 1)


@bp.post("/documents/<int:document_id>/delete")
def delete_document(document_id):
    document = db.get_document(document_id) or abort(404)
    db.delete_document(document_id)
    flash(f"“{document['filename']}” deleted.", "ok")
    return redirect(url_for("songs.detail", song_id=document["song_id"]))
