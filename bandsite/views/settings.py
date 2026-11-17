"""Band-wide settings: rehearsal day and time."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db
from . import rehearsals

bp = Blueprint("settings", __name__)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@bp.before_request
@login_required
def _require_login():
    pass


@bp.route("/settings", methods=["GET", "POST"])
def index():
    current = db.get_settings()
    if request.method == "POST":
        weekday = request.form.get("rehearsal_weekday", "")
        time = request.form.get("rehearsal_time", "").strip()[:5]
        errors = []
        if weekday not in [str(i) for i in range(7)]:
            errors.append("Choose a rehearsal day.")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time):
            errors.append("Enter the time as hours and minutes, for example 17:30.")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("settings.html", s={**current, "rehearsal_weekday": weekday, "rehearsal_time": time}, weekdays=WEEKDAYS)

        db.save_settings({"rehearsal_weekday": weekday, "rehearsal_time": time}, current_user.id)
        flash("Settings saved.", "ok")

        old_day, new_day = int(current["rehearsal_weekday"]), int(weekday)
        if old_day != new_day:
            today = rehearsals.today()
            kept = db.remove_unused_rehearsals(today, old_day)
            db.ensure_rehearsals(rehearsals.upcoming_rehearsal_days(today, new_day))
            flash(f"Rehearsals are on {WEEKDAYS[new_day]} now; the next three months are planned.", "ok")
            if kept:
                dates = ", ".join(d.strftime("%a, %d %b") for d in kept)
                flash(f"These {WEEKDAYS[old_day]} rehearsals already have answers or a plan, so they stay: {dates}. "
                      "Cancel them on their page if they don't take place.", "error")
        return redirect(url_for("settings.index"))
    return render_template("settings.html", s=current, weekdays=WEEKDAYS)
