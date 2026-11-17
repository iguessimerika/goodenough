"""Rehearsals: on the band's rehearsal day (see Settings), created automatically for the next three months.

Members say yes or no. Saying no after the Saturday before the rehearsal means bringing food
next time (see the band member page). From the yes answers and the members' instruments the
page shows whether the rehearsal is likely to happen.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db

bp = Blueprint("rehearsals", __name__)

BAND_TIMEZONE = ZoneInfo("Europe/Berlin")
WEEKS_AHEAD = 13           # about three months

# Instrument labels from the keyword "Instrument" that the outlook looks at (compared without case).
SINGER = "gesang"
NEEDED_FOR_YES = ("gitarre", "gesang", "schlagzeug")


@bp.before_request
@login_required
def _require_login():
    pass


# ---------------------------------------------------------------- dates

def today():
    """Today in the band's time zone (the server itself runs in UTC)."""
    return datetime.now(BAND_TIMEZONE).date()


def rehearsal_settings():
    """(weekday 0-6, start time 'HH:MM') from the band settings."""
    values = db.get_settings()
    return int(values["rehearsal_weekday"]), values["rehearsal_time"]


def upcoming_rehearsal_days(start, weekday, weeks=WEEKS_AHEAD):
    first = start + timedelta(days=(weekday - start.weekday()) % 7)
    return [first + timedelta(weeks=i) for i in range(weeks)]


def deadline_for(rehearsal_date):
    """The Saturday before the rehearsal; cancelling is free until the end of that day."""
    days_back = (rehearsal_date.weekday() - 5) % 7 or 7
    return rehearsal_date - timedelta(days=days_back)


def food_rule_applies(rehearsal):
    """Late cancelling only costs food if the rehearsal already existed by its deadline.

    Rehearsals added at short notice (an extra date, or right after changing the rehearsal day)
    can be cancelled for free.
    """
    created = rehearsal.get("created_at")
    if not isinstance(created, datetime):
        return True
    created_local = created.replace(tzinfo=timezone.utc).astimezone(BAND_TIMEZONE).date()  # MySQL stores UTC
    return created_local <= deadline_for(rehearsal["rehearsal_date"])


def is_late(rehearsal, now):
    return now > deadline_for(rehearsal["rehearsal_date"]) and food_rule_applies(rehearsal)


# ---------------------------------------------------------------- will it happen?

def outlook(rehearsal, members, instruments):
    """Returns (state, explanation). state is 'yes', 'maybe', 'no' or 'cancelled'.

    For now: guitar, vocals and drums are in → yes; at least one singer and one other
    instrument → maybe; otherwise no. Kept in one place so the rule is easy to change.
    """
    if rehearsal["is_cancelled"]:
        return "cancelled", rehearsal["cancel_reason"] or "Cancelled"
    coming = [m["id"] for m in members if rehearsal["responses"].get(m["id"]) == "yes"]
    labels = {label.lower() for member_id in coming for label in instruments.get(member_id, ())}
    missing = [needed for needed in NEEDED_FOR_YES if needed not in labels]
    if not missing:
        return "yes", "Guitar, vocals and drums are in."
    if SINGER in labels and labels - {SINGER}:
        return "maybe", "Still missing: " + ", ".join(_nice(m) for m in missing)
    if not coming:
        return "no", "Nobody has said yes yet."
    return "no", "Needs at least one singer and one instrument."


def _nice(label):
    return {"gitarre": "Gitarre", "gesang": "Gesang", "schlagzeug": "Schlagzeug"}.get(label, label)


def _decorate(rehearsals, members, instruments, now):
    """Adds what the templates need: outlook, who said what, deadline, my answer."""
    names = {m["id"]: m["name"] for m in members}
    for r in rehearsals:
        r["state"], r["state_text"] = outlook(r, members, instruments)
        r["yes"] = [m for m in members if r["responses"].get(m["id"]) == "yes"]
        r["no"] = [m for m in members if r["responses"].get(m["id"]) == "no"]
        r["open"] = [m for m in members if m["id"] not in r["responses"]]
        r["deadline"] = deadline_for(r["rehearsal_date"])
        r["is_past"] = r["rehearsal_date"] < now
        r["is_today"] = r["rehearsal_date"] == now
        r["deadline_passed"] = is_late(r, now)
        r["short_notice"] = not food_rule_applies(r)
        r["mine"] = r["responses"].get(current_user.id)
        r["can_answer"] = not r["is_past"] and not r["is_cancelled"]
        for m in r["yes"] + r["no"]:
            m.setdefault("instruments_text", ", ".join(sorted(instruments.get(m["id"], ()))))
    return names


def _members():
    return [{"id": m["id"], "name": m["name"]} for m in db.list_members()]


# ---------------------------------------------------------------- pages

@bp.get("/rehearsal")
def index():
    now = today()
    weekday, start_time = rehearsal_settings()
    db.ensure_rehearsals(upcoming_rehearsal_days(now, weekday))
    show_past = request.args.get("past") == "1"
    rehearsals = db.list_rehearsals(None if show_past else now)
    members = _members()
    _decorate(rehearsals, members, db.list_member_instruments(), now)
    upcoming = [r for r in rehearsals if not r["is_past"]]
    next_rehearsal = next((r for r in upcoming if not r["is_cancelled"]), None)
    return render_template(
        "rehearsals/index.html",
        rehearsals=rehearsals,
        next_rehearsal=next_rehearsal,
        show_past=show_past,
        past_count=db.count_past_rehearsals(now),
        food=db.list_open_food_duties(),
        today=now,
        weekday_name=date(2024, 1, 1 + weekday).strftime("%A"),  # 1 Jan 2024 was a Monday
        start_time=start_time,
    )


@bp.get("/rehearsal/<int:rehearsal_id>")
def detail(rehearsal_id):
    rehearsal = db.get_rehearsal(rehearsal_id) or abort(404)
    now = today()
    members = _members()
    instruments = db.list_member_instruments()
    _decorate([rehearsal], members, instruments, now)
    late = {f["member_id"] for f in db.list_open_food_duties() if f["rehearsal_date"] == rehearsal["rehearsal_date"]}
    planned = {s["id"] for s in rehearsal["songs"]}
    return render_template(
        "rehearsals/detail.html",
        r=rehearsal,
        late=late,
        setlists=db.list_setlists(),
        songs=[s for s in db.list_song_choices() if s["id"] not in planned],
        start_time=rehearsal_settings()[1],
        has_sheets=bool(rehearsal["setlist_id"])
        and (db.get_setlist_with_sheets(rehearsal["setlist_id"]) or {}).get("document_count", 0) > 0,
    )


def _back(rehearsal_id=None):
    if request.form.get("back") == "index" or rehearsal_id is None:
        anchor = f"#rehearsal-{rehearsal_id}" if rehearsal_id else ""
        past = "?past=1" if request.form.get("past") == "1" else ""
        return redirect(url_for("rehearsals.index") + past + anchor)
    return redirect(url_for("rehearsals.detail", rehearsal_id=rehearsal_id))


@bp.post("/rehearsal/<int:rehearsal_id>/respond")
def respond(rehearsal_id):
    rehearsal = db.get_rehearsal(rehearsal_id) or abort(404)
    status = request.form.get("status")
    if status not in ("yes", "no"):
        abort(400)
    now = today()
    when = rehearsal["rehearsal_date"].strftime("%a, %d %b")
    if rehearsal["rehearsal_date"] < now:
        flash("This rehearsal is already over.", "error")
    elif rehearsal["is_cancelled"]:
        flash("This rehearsal is cancelled.", "error")
    else:
        late = is_late(rehearsal, now)
        owes = db.set_response(rehearsal_id, current_user.id, status, late)
        if owes:
            flash(f"Got it, you can't make it on {when}. That's after Saturday, so you're bringing food next time.", "error")
        elif status == "yes":
            flash(f"You're in for {when}.", "ok")
        else:
            flash(f"Got it, you can't make it on {when}.", "ok")
    return _back(rehearsal_id)


@bp.post("/rehearsal/<int:rehearsal_id>/plan")
def plan(rehearsal_id):
    db.get_rehearsal(rehearsal_id) or abort(404)
    raw = request.form.get("setlist_id", "")
    setlist_id = int(raw) if raw.isdigit() and db.get_setlist(int(raw)) else None
    notes = request.form.get("notes", "").strip()
    if len(notes) > 5000:
        flash("The notes can have 5000 characters at most.", "error")
    else:
        db.update_rehearsal_plan(rehearsal_id, setlist_id, notes)
        flash("Plan saved.", "ok")
    return _back(rehearsal_id)


@bp.post("/rehearsal/<int:rehearsal_id>/songs")
def add_song(rehearsal_id):
    db.get_rehearsal(rehearsal_id) or abort(404)
    raw = request.form.get("song_id", "")
    if raw.isdigit() and db.song_exists(int(raw)):
        db.add_song_to_rehearsal(rehearsal_id, int(raw))
    else:
        flash("Choose a song to add.", "error")
    return _back(rehearsal_id)


@bp.post("/rehearsal/<int:rehearsal_id>/songs/<int:song_id>/remove")
def remove_song(rehearsal_id, song_id):
    db.remove_song_from_rehearsal(rehearsal_id, song_id)
    return _back(rehearsal_id)


@bp.post("/rehearsal/<int:rehearsal_id>/cancel")
def cancel(rehearsal_id):
    rehearsal = db.get_rehearsal(rehearsal_id) or abort(404)
    if request.form.get("action") == "restore":
        db.set_rehearsal_cancelled(rehearsal_id, False, None)
        flash("The rehearsal is back on the plan.", "ok")
    else:
        reason = request.form.get("reason", "").strip()[:200]
        db.set_rehearsal_cancelled(rehearsal_id, True, reason)
        flash(f"Rehearsal on {rehearsal['rehearsal_date'].strftime('%a, %d %b')} cancelled. Nobody owes food for it.", "ok")
    return _back(rehearsal_id)


@bp.post("/rehearsal/new")
def new():
    raw = request.form.get("rehearsal_date", "")
    try:
        when = date.fromisoformat(raw)
    except ValueError:
        flash("Choose a date for the extra rehearsal.", "error")
        return redirect(url_for("rehearsals.index"))
    if when < today():
        flash("That date is in the past.", "error")
        return redirect(url_for("rehearsals.index"))
    rehearsal_id = db.create_rehearsal(when)
    if rehearsal_id is None:
        flash("There already is a rehearsal on that day.", "error")
        return redirect(url_for("rehearsals.index"))
    flash(f"Extra rehearsal on {when.strftime('%a, %d %b')} added.", "ok")
    return redirect(url_for("rehearsals.detail", rehearsal_id=rehearsal_id))


@bp.post("/rehearsal/cleanup")
def cleanup():
    removed = db.delete_past_rehearsals(today())
    if removed:
        flash(f"{removed} past rehearsal{'' if removed == 1 else 's'} deleted. Open food duties are kept.", "ok")
    else:
        flash("There were no past rehearsals to delete.", "ok")
    return redirect(url_for("rehearsals.index"))


@bp.post("/food/<int:duty_id>/settle")
def settle_food(duty_id):
    duty = db.get_food_duty(duty_id) or abort(404)
    db.settle_food_duty(duty_id, current_user.id)
    flash(f"Thanks to {duty['name']} for the food!", "ok")
    target = request.form.get("back")
    if target == "rehearsals":
        return redirect(url_for("rehearsals.index"))
    return redirect(url_for("main.members") + "#food")
