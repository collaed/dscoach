"""Coachee blueprint: all /me/* routes plus task attachment, voice, progress-photo serving."""

import base64
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, flash, redirect, render_template_string, request, session, url_for

from auth import login_required
from automation import (
    _check_and_award_badges,
    _completion_hours,
    _compute_level,
    _get_badges,
    _get_rituals,
    _mood_sparkline,
    _ritual_status_today,
    _run_auto_rules,
    _weekly_report,
)
from helpers import ATTACHMENTS_DIR, _tpl, db, ensure_aware, utcnow
from merge import _merge_vars
from tasks import FEATURES, _auto_assign_reserves, _features_for, _freeze_overdue, _run_onboarding, _update_streak, _visible_tasks

bp = Blueprint("coachee", __name__)



@bp.route("/me")
@login_required("coachee")
def coachee_dashboard():
    """PURPOSE: Assemble the coachee home screen — auto-assign reserves, freeze overdue, update streak, award badges, run onboarding, then gather tasks, conditioning, check-ins, acks, notes, tracking, goals, journals, voice notes, photos, rituals and writing stats.
    CALLED BY: Route GET /me — renders coachee_dashboard.html; primary redirect target after coachee login and most /me* POST handlers.
    WHEN: On every coachee dashboard load."""
    c = db()
    cid = session["user_id"]
    c.execute("SELECT * FROM coachee WHERE id=%s", (cid,))
    coachee = c.fetchone()

    # auto-assign reserve if past unveil time and no task today
    tz = ZoneInfo(coachee["timezone"] or "UTC")
    local_now = datetime.now(tz)
    current_time = local_now.time()
    unveil = coachee["task_unveil_time"]
    if unveil:
        if isinstance(unveil, timedelta):
            unveil_hour = int(unveil.total_seconds()) // 3600
            unveil_min = (int(unveil.total_seconds()) % 3600) // 60
        elif isinstance(unveil, str):
            parts = unveil.split(":")
            unveil_hour, unveil_min = int(parts[0]), int(parts[1])
        else:
            unveil_hour, unveil_min = unveil.hour, unveil.minute
        from datetime import time as _time

        if current_time >= _time(unveil_hour, unveil_min):
            _auto_assign_reserves(cid, coachee["coach_id"])

    _freeze_overdue(cid, tz)
    _update_streak(cid, tz)
    _check_and_award_badges(cid)

    # Onboarding: auto-deliver steps for new coachees
    created = coachee.get("created_at")
    if created:
        from datetime import date as _date
        if isinstance(created, str):
            try:
                created_date = datetime.fromisoformat(created.split(" ")[0]).date()
            except ValueError:
                created_date = _date.today()
        elif hasattr(created, "date"):
            created_date = created.date()
        else:
            created_date = _date.today()
        days_active = (_date.today() - created_date).days
        _run_onboarding(cid, coachee["coach_id"], days_active)

    tasks = _visible_tasks(cid, tz)
    local_today = datetime.now(tz).date().isoformat()

    c.execute(
        """SELECT mc.* FROM mental_conditioning mc
                 WHERE (mc.target='all' OR mc.coachee_id=%s) AND mc.prompt_date=%s
                 AND mc.id NOT IN (SELECT conditioning_id FROM mental_conditioning_response WHERE coachee_id=%s)""",
        (cid, local_today, cid),
    )
    conditioning = c.fetchall()
    c.execute(
        "SELECT * FROM checkin WHERE coachee_id=%s AND DATE(created_at)=%s ORDER BY created_at", (cid, local_today)
    )
    today_checkins = c.fetchall()
    c.execute("SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    acks = c.fetchall()
    now_str = utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "SELECT * FROM note WHERE coachee_id=%s AND (scheduled_at IS NULL OR scheduled_at <= %s) ORDER BY created_at DESC LIMIT 10",
        (cid, now_str),
    )
    notes = c.fetchall()
    # mark unread coach notes as read
    c.execute(
        "UPDATE note SET read_at=%s WHERE coachee_id=%s AND author_role='coach' AND read_at IS NULL AND (scheduled_at IS NULL OR scheduled_at <= %s)",
        (now_str, cid, now_str),
    )
    c.execute(
        "SELECT * FROM tracking_log WHERE coachee_id=%s AND DATE(created_at)=%s ORDER BY created_at", (cid, local_today)
    )
    today_tracking = c.fetchall()

    has_morning = any(ci["checkin_type"] == "morning" for ci in today_checkins)
    has_evening = any(ci["checkin_type"] == "evening" for ci in today_checkins)
    pending_conditioning = len(conditioning)

    badges = {
        "tasks": len(tasks),
        "morning": 0 if has_morning else 1,
        "evening": 0 if has_evening else 1,
        "conditioning": pending_conditioning,
        "notes": 0,
    }

    c.execute(
        """SELECT ta.*, tt.title FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.grade IS NOT NULL ORDER BY ta.responded_at DESC LIMIT 10""",
        (cid,),
    )
    graded_tasks = c.fetchall()

    c.execute(
        "SELECT * FROM goal WHERE coachee_id=%s ORDER BY CASE status WHEN 'active' THEN 1 WHEN 'approved' THEN 2 WHEN 'proposed' THEN 3 WHEN 'completed' THEN 4 ELSE 5 END, created_at DESC",
        (cid,),
    )
    goals = c.fetchall()
    c.execute("SELECT * FROM journal WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    journals = c.fetchall()
    c.execute("SELECT * FROM voice_note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    voice_notes = c.fetchall()
    c.execute("SELECT * FROM progress_photo WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    photos = c.fetchall()

    # Creative writing stats for dashboard
    c.execute("SELECT COUNT(*) as cnt FROM creative_work WHERE coachee_id=%s", (cid,))
    writing_count = c.fetchone()["cnt"]
    c.execute(
        "SELECT COUNT(*) as cnt FROM creative_constraint WHERE coachee_id=%s AND used=0", (cid,)
    )
    writing_pending_constraints = c.fetchone()["cnt"]

    return render_template_string(
        _tpl("coachee_dashboard.html"),
        coachee=coachee,
        tasks=tasks,
        conditioning=[{**mc, "prompt_text": _merge_vars(mc.get("prompt_text", ""), cid)} for mc in conditioning],
        today_checkins=today_checkins,
        acks=acks,
        notes=[{**n, "content": _merge_vars(n.get("content", ""), cid)} for n in notes],
        today_tracking=today_tracking,
        badges=badges,
        graded_tasks=graded_tasks,
        goals=goals,
        journals=journals,
        voice_notes=voice_notes,
        photos=photos,
        feat=_features_for(coachee["coach_id"], cid),
        weekly_report=_weekly_report(cid),
        earned_badges=_get_badges(cid),
        mood_data=_mood_sparkline(cid),
        level_info=_compute_level(cid, coachee["coach_id"]),
        rituals=[{**r, "description": _merge_vars(r.get("description", ""), cid)} for r in _get_rituals(cid, coachee["coach_id"])],
        rituals_done=_ritual_status_today(cid, _get_rituals(cid, coachee["coach_id"]), local_today),
        local_today=local_today,
        writing_count=writing_count,
        writing_pending_constraints=writing_pending_constraints,
    )



@bp.route("/me/checkin", methods=["POST"])
@login_required("coachee")
def submit_checkin():
    """PURPOSE: Persist a morning/evening/weekly check-in (with optional mood) and fire the checkin_submitted automation rules.
    CALLED BY: Route POST /me/checkin — check-in form on coachee_dashboard.html; redirects back to the coachee dashboard.
    WHEN: On submitting a check-in."""
    c = db()
    mood = request.form.get("mood")
    if mood:
        try:
            c.execute(
                "INSERT INTO checkin (coachee_id, checkin_type, content, mood) VALUES (%s,%s,%s,%s)",
                (session["user_id"], request.form["checkin_type"], request.form["content"], int(mood)),
            )
        except Exception:
            c.execute(
                "INSERT INTO checkin (coachee_id, checkin_type, content) VALUES (%s,%s,%s)",
                (session["user_id"], request.form["checkin_type"], request.form["content"]),
            )
    else:
        c.execute(
            "INSERT INTO checkin (coachee_id, checkin_type, content) VALUES (%s,%s,%s)",
            (session["user_id"], request.form["checkin_type"], request.form["content"]),
        )
    flash("Check-in submitted.", "success")
    _run_auto_rules(session["user_id"], "checkin_submitted")
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/task/<int:tid>", methods=["POST"])
@login_required("coachee")
def complete_task(tid):
    """PURPOSE: Record a coachee's task response (status, text, optional image attachment, reflection), then run automation rules, optional AI photo validation, and auto-grading.
    CALLED BY: Route POST /me/task/<tid> — task submission form on coachee_dashboard.html; redirects back to the coachee dashboard.
    WHEN: On submitting a task response."""
    c = db()
    c.execute("SELECT frozen_after, template_id FROM task_assignment WHERE id=%s AND coachee_id=%s", (tid, session["user_id"]))
    row = c.fetchone()
    if not row:
        return redirect(url_for("coachee.coachee_dashboard"))
    if row["frozen_after"]:
        frozen = ensure_aware(row["frozen_after"])
        if utcnow() > frozen:
            return redirect(url_for("coachee.coachee_dashboard"))
    template_id = row["template_id"]
    att_path = None
    att_data = request.form.get("attachment_data")
    if att_data and att_data.startswith("data:image"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        att_path = f"{ATTACHMENTS_DIR}/{session['user_id']}_{tid}_{int(utcnow().timestamp())}.jpg"
        with open(att_path, "wb") as f:
            f.write(base64.b64decode(att_data.split(",", 1)[1]))
    status = request.form.get("status", "completed")
    if status not in ("completed", "partial"):
        status = "completed"
    c.execute(
        """UPDATE task_assignment SET status=%s, response=%s, attachment_path=%s, responded_at=%s,
                 reflection_rating=%s, reflection_text=%s
                 WHERE id=%s AND coachee_id=%s""",
        (
            status,
            request.form["response"],
            att_path,
            utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            request.form.get("reflection_rating") or None,
            request.form.get("reflection_text") or None,
            tid,
            session["user_id"],
        ),
    )
    flash("Task submitted!", "success")
    _run_auto_rules(session["user_id"], "task_completed")

    # Photo validation: run AI check if enabled and photo attached
    if att_path and status == "completed":
        from photo_validation import should_validate_photo, validate_photo_proof

        coach_id = session.get("coach_id")
        if coach_id and should_validate_photo(coach_id, session["user_id"], template_id):
            c.execute("SELECT title, description FROM task_template WHERE id=%s", (template_id,))
            tmpl = c.fetchone()
            if tmpl:
                try:
                    validate_photo_proof(tid, att_path, tmpl["title"], tmpl.get("description", ""), coach_id)
                except Exception:
                    pass  # Non-blocking: validation failure doesn't affect submission

    # Auto-grading: if template is marked auto_grade, grade immediately
    if status == "completed":
        c.execute(
            "SELECT tt.auto_grade FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id WHERE ta.id=%s",
            (tid,),
        )
        tpl_row = c.fetchone()
        if tpl_row and tpl_row.get("auto_grade"):
            response_text = request.form.get("response", "")
            resp_len = len(response_text.strip())
            if resp_len >= 150:
                auto_g = "A"
            elif resp_len >= 80:
                auto_g = "B"
            elif resp_len >= 30:
                auto_g = "C"
            else:
                auto_g = "D"
            c.execute(
                "UPDATE task_assignment SET grade=%s, coach_comment=%s WHERE id=%s",
                (auto_g, "[Auto-graded]", tid),
            )
    return redirect(url_for("coachee.coachee_dashboard"))



@bp.route("/me/conditioning/<int:mid>", methods=["POST"])
@login_required("coachee")
def respond_conditioning(mid):
    """PURPOSE: Store a coachee's response to a mental-conditioning prompt.
    CALLED BY: Route POST /me/conditioning/<mid> — conditioning response form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On answering a daily conditioning prompt."""
    c = db()
    c.execute(
        "INSERT INTO mental_conditioning_response (conditioning_id, coachee_id, content) VALUES (%s,%s,%s)",
        (mid, session["user_id"], request.form["content"]),
    )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/tracking", methods=["POST"])
@login_required("coachee")
def submit_tracking():
    """PURPOSE: Log a tracking entry (food/hydration/alcohol/exercise/emotional) for the coachee.
    CALLED BY: Route POST /me/tracking — tracking form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On submitting a tracking entry."""
    c = db()
    c.execute(
        "INSERT INTO tracking_log (coachee_id, category, content) VALUES (%s,%s,%s)",
        (session["user_id"], request.form["category"], request.form["content"]),
    )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/note", methods=["POST"])
@login_required("coachee")
def coachee_add_note():
    """PURPOSE: Post a note from the coachee to their coach (async bidirectional messaging).
    CALLED BY: Route POST /me/note — note form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On sending a note to the coach."""
    c = db()
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coachee',%s)",
        (session["user_id"], request.form["content"]),
    )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/pause", methods=["POST"])
@login_required("coachee")
def trigger_pause():
    """PURPOSE: Activate a pause/safe-word freeze for the coachee via the freeze service.
    CALLED BY: Route POST /me/pause — pause/safe-word control on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On the coachee triggering a pause or safe word."""
    from services.freeze import activate
    word = request.form.get("word", "pause")
    use_safeword = word.upper() == session.get("safe_word", "RED") or word.upper() == "RED"
    activate(session["user_id"], initiated_by="coachee", use_safeword=use_safeword)
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/history")
@login_required("coachee")
def coachee_history():
    """PURPOSE: Gather the coachee's recent check-ins, tracking logs and notes (last 50 each) for review.
    CALLED BY: Route GET /me/history — renders coachee_history.html, the coachee history screen.
    WHEN: On opening the coachee history screen."""
    c = db()
    cid = session["user_id"]
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    checkins = c.fetchall()
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    logs = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    notes = c.fetchall()
    return render_template_string(_tpl("coachee_history.html"), checkins=checkins, logs=logs, notes=notes)



@bp.route("/me/voice", methods=["POST"])
@login_required("coachee")
def coachee_voice_note():
    """PURPOSE: Decode a base64 audio recording, save it to attachments, and record a coachee voice note with duration.
    CALLED BY: Route POST /me/voice — voice-recorder control on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On submitting a recorded voice note."""
    c = db()
    audio = request.form.get("audio_data")
    if audio and audio.startswith("data:audio"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/voice_{session['user_id']}_{int(utcnow().timestamp())}.webm"
        with open(path, "wb") as f:
            f.write(base64.b64decode(audio.split(",", 1)[1]))
        dur = int(request.form.get("duration", 0))
        c.execute(
            "INSERT INTO voice_note (coachee_id, author_role, file_path, duration_sec) VALUES (%s,'coachee',%s,%s)",
            (session["user_id"], path, dur),
        )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/voice/<int:vid>")
def serve_voice(vid):
    """PURPOSE: Stream a stored voice-note audio file, enforcing that a coachee may only fetch their own; coaches allowed.
    CALLED BY: Route GET /voice/<vid> — <audio> src references in coachee_dashboard.html and coach_view_coachee.html; requires a session.
    WHEN: On the browser loading/playing a voice note."""
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    c = db()
    c.execute("SELECT file_path, coachee_id FROM voice_note WHERE id=%s", (vid,))
    row = c.fetchone()
    if not row:
        abort(404)
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        abort(403)
    try:
        with open(row["file_path"], "rb") as f:
            data = f.read()
        return Response(data, mimetype="audio/webm")
    except FileNotFoundError:
        abort(404)


@bp.route("/me/goal", methods=["POST"])
@login_required("coachee")
def propose_goal():
    """PURPOSE: Create a coachee-proposed goal (enters the coach approval workflow in status 'proposed').
    CALLED BY: Route POST /me/goal — goal proposal form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On proposing a new goal."""
    c = db()
    c.execute(
        "INSERT INTO goal (coachee_id, title, description) VALUES (%s,%s,%s)",
        (session["user_id"], request.form["title"], request.form.get("description", "")),
    )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/me/journal", methods=["POST"])
@login_required("coachee")
def add_journal():
    """PURPOSE: Save a coachee journal entry, flagged private or visible to the coach.
    CALLED BY: Route POST /me/journal — journal form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On saving a journal entry."""
    c = db()
    visible = 1 if request.form.get("visible_to_coach") else 0
    c.execute(
        "INSERT INTO journal (coachee_id, content, visible_to_coach) VALUES (%s,%s,%s)",
        (session["user_id"], request.form["content"], visible),
    )
    return redirect(url_for("coachee.coachee_dashboard"))



@bp.route("/me/progress-photo", methods=["POST"])
@login_required("coachee")
def add_progress_photo():
    """PURPOSE: Decode a base64 image, save it to attachments, and record a progress photo with caption.
    CALLED BY: Route POST /me/progress-photo — progress-photo capture form on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On uploading a progress photo."""
    img_data = request.form.get("photo_data")
    if img_data and img_data.startswith("data:image"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/progress_{session['user_id']}_{int(utcnow().timestamp())}.jpg"
        with open(path, "wb") as f:
            f.write(base64.b64decode(img_data.split(",", 1)[1]))
        c = db()
        c.execute(
            "INSERT INTO progress_photo (coachee_id, file_path, caption) VALUES (%s,%s,%s)",
            (session["user_id"], path, request.form.get("caption", "")),
        )
    return redirect(url_for("coachee.coachee_dashboard"))


@bp.route("/progress-photo/<int:pid>")
def serve_progress_photo(pid):
    """PURPOSE: Stream a stored progress-photo file, enforcing that a coachee may only fetch their own; coaches allowed.
    CALLED BY: Route GET /progress-photo/<pid> — <img> src references in coachee_dashboard.html and coach_view_coachee.html; requires a session.
    WHEN: On the browser loading a progress photo."""
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    c = db()
    c.execute("SELECT file_path, coachee_id FROM progress_photo WHERE id=%s", (pid,))
    row = c.fetchone()
    if not row:
        abort(404)
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        abort(403)
    try:
        with open(row["file_path"], "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/jpeg")
    except FileNotFoundError:
        abort(404)


@bp.route("/task/<int:tid>/attachment")
def task_attachment(tid):
    """PURPOSE: Stream a task's proof-image attachment, enforcing that a coachee may only fetch their own; coaches allowed.
    CALLED BY: Route GET /task/<tid>/attachment — <img> src references in coachee_dashboard.html and coach_view_coachee.html; requires a session.
    WHEN: On the browser loading a task attachment image."""
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    c = db()
    c.execute("SELECT attachment_path, coachee_id FROM task_assignment WHERE id=%s", (tid,))
    row = c.fetchone()
    if not row or not row["attachment_path"]:
        abort(404)
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        abort(403)
    try:
        with open(row["attachment_path"], "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/jpeg")
    except FileNotFoundError:
        abort(404)


@bp.route("/me/export")
@login_required("coachee")
def data_export():
    """PURPOSE: Build a full JSON export of the coachee's own data (profile, check-ins, tasks, tracking, notes, acknowledgements) as a downloadable file.
    CALLED BY: Route GET /me/export — data-export/download link on coachee screens; returns a JSON attachment.
    WHEN: On requesting a personal data export."""
    c = db()
    cid = session["user_id"]
    data = {}
    c.execute("SELECT name, username, created_at, contract_text, safe_word, status FROM coachee WHERE id=%s", (cid,))
    data["profile"] = dict(c.fetchone())
    for table, q in [
        ("checkins", "SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at"),
        (
            "tasks",
            """SELECT ta.*, tt.title, tt.description as task_desc FROM task_assignment ta
                                  JOIN task_template tt ON ta.template_id=tt.id WHERE ta.coachee_id=%s ORDER BY ta.created_at""",
        ),
        ("tracking", "SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at"),
        ("notes", "SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at"),
        ("acknowledgements", "SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at"),
    ]:
        c.execute(q, (cid,))
        data[table] = [dict(r) for r in c.fetchall()]

    return Response(
        json.dumps(data, default=str, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=my_data_{cid}.json"},
    )


@bp.route("/me/ritual/<int:rid>/complete", methods=["POST"])
@login_required("coachee")
def complete_ritual(rid):
    """PURPOSE: Log completion of a ritual for today (idempotent — unique per ritual/coachee/day).
    CALLED BY: Route POST /me/ritual/<rid>/complete — ritual completion buttons on coachee_dashboard.html; redirects back to the dashboard.
    WHEN: On marking a ritual done for the day."""
    c = db()
    cid = session["user_id"]
    tz = ZoneInfo(session.get("timezone", "UTC"))
    today = datetime.now(tz).date().isoformat()
    try:
        c.execute(
            "INSERT INTO ritual_log (ritual_id, coachee_id, completed_date) VALUES (%s,%s,%s)",
            (rid, cid, today),
        )
    except Exception:
        pass  # unique constraint — already logged today
    return redirect(url_for("coachee.coachee_dashboard"))



# ── Creative Writing ──


@bp.route("/me/writing", methods=["GET"])
@login_required("coachee")
def writing_collection():
    """PURPOSE: View all of the coachee's creative works, active (unused) constraints, and collections.
    CALLED BY: Route GET /me/writing — renders writing.html, the coachee creative-writing screen.
    WHEN: On opening the writing collection screen."""
    c = db()
    cid = session["user_id"]
    c.execute("SELECT * FROM creative_work WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    works = c.fetchall()
    c.execute(
        "SELECT * FROM creative_constraint WHERE coachee_id=%s AND used=0 ORDER BY active_date, created_at",
        (cid,),
    )
    constraints = c.fetchall()
    c.execute("SELECT * FROM creative_collection WHERE coachee_id=%s ORDER BY created_at", (cid,))
    collections = c.fetchall()
    total = len(works)
    return render_template_string(
        _tpl("writing.html"),
        works=works,
        constraints=constraints,
        collections=collections,
        total=total,
    )


@bp.route("/me/writing/submit", methods=["POST"])
@login_required("coachee")
def submit_work():
    """PURPOSE: Submit a new creative work (poem/prose/journal) with type/tags, optionally linked to a collection and marking its constraint used.
    CALLED BY: Route POST /me/writing/submit — submission form on writing.html; redirects back to the writing collection screen.
    WHEN: On submitting a creative work."""
    c = db()
    cid = session["user_id"]
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    work_type = request.form.get("work_type", "poem")
    tags = request.form.get("tags", "").strip()
    constraint_id = request.form.get("constraint_id") or None
    collection_id = request.form.get("collection_id") or None

    if not content:
        flash("Content is required.", "error")
        return redirect(url_for("coachee.writing_collection"))

    c.execute(
        """INSERT INTO creative_work
           (coachee_id, collection_id, constraint_id, title, content, work_type, tags)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (cid, collection_id, constraint_id, title, content, work_type, tags),
    )

    # Mark constraint as used if provided
    if constraint_id:
        c.execute("UPDATE creative_constraint SET used=1 WHERE id=%s AND coachee_id=%s", (constraint_id, cid))

    flash("Work submitted.", "success")
    return redirect(url_for("coachee.writing_collection"))


@bp.route("/me/writing/<int:wid>")
@login_required("coachee")
def view_work(wid):
    """PURPOSE: View a single creative work owned by the coachee, plus its linked constraint if any.
    CALLED BY: Route GET /me/writing/<wid> — renders writing_view.html; linked from work listings on writing.html.
    WHEN: On opening an individual creative work."""
    c = db()
    cid = session["user_id"]
    c.execute("SELECT * FROM creative_work WHERE id=%s AND coachee_id=%s", (wid, cid))
    work = c.fetchone()
    if not work:
        abort(404)
    constraint = None
    if work.get("constraint_id"):
        c.execute("SELECT * FROM creative_constraint WHERE id=%s", (work["constraint_id"],))
        constraint = c.fetchone()
    return render_template_string(_tpl("writing_view.html"), work=work, constraint=constraint)


@bp.route("/me/help")
@login_required("coachee")
def coachee_help():
    """PURPOSE: Render the in-app navigation/help guide for coachees.
    CALLED BY: Route GET /me/help — renders coachee_help.html, the coachee help screen (linked from dashboard nav).
    WHEN: On opening the coachee help screen."""
    return render_template_string(_tpl("coachee_help.html"))
