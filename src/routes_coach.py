"""Coach blueprint: all /coach/* routes."""

import base64
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, flash, redirect, render_template_string, request, session, url_for

from ai import LLM_KEY, _build_profile_prompt, _cf_ai_complete
from auth import login_required
from automation import _completion_hours, _engagement_score, _payment_compliance, _weekly_report
from helpers import ATTACHMENTS_DIR, _audit, _hash, _hash_password, _tpl, _verify_password, db, utcnow
from merge import _merge_vars
from tasks import FEATURES, _features_for

bp = Blueprint("coach", __name__)



@bp.route("/coach")
@login_required("coach")
def coach_dashboard():
    """Build per-coachee stats (tasks, grades, streaks, engagement, payment compliance).

    Route GET /coach — renders the coach dashboard screen (coach_dashboard.html).
    When: on dashboard load, the coach's landing screen after login.
    """
    c = db()
    c.execute("SELECT * FROM coachee WHERE coach_id=%s ORDER BY name", (session["user_id"],))
    coachees = c.fetchall()
    for cc in coachees:
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s", (cc["id"],))
        cc["total_tasks"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='completed'", (cc["id"],))
        cc["completed_tasks"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='pending'", (cc["id"],))
        cc["pending_tasks"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='missed'", (cc["id"],))
        cc["missed_tasks"] = c.fetchone()["cnt"]
        c.execute(
            "SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='completed' AND grade IS NULL",
            (cc["id"],),
        )
        cc["ungraded"] = c.fetchone()["cnt"]
        c.execute(
            "SELECT AVG(CASE grade WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6 END) as avg_g FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL",
            (cc["id"],),
        )
        avg = c.fetchone()["avg_g"]
        cc["avg_grade"] = chr(64 + round(avg)) if avg else "\u2014"
        cc["strikes"] = cc.get("strikes") or 0
        cc["current_streak"] = cc.get("current_streak") or 0
        c.execute(
            "SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s AND DATE(created_at)=%s",
            (cc["id"], datetime.now(ZoneInfo(cc["timezone"] or "UTC")).date().isoformat()),
        )
        cc["checkins_today"] = c.fetchone()["cnt"]
        cc["engagement"] = _engagement_score(cc["id"])
        # Inactivity detection: days since last check-in
        c.execute(
            "SELECT MAX(created_at) as last_checkin FROM checkin WHERE coachee_id=%s", (cc["id"],)
        )
        last_row = c.fetchone()
        if last_row and last_row["last_checkin"]:
            last_ci = last_row["last_checkin"]
            if isinstance(last_ci, str):
                try:
                    last_ci = datetime.fromisoformat(last_ci.replace("T", " ").split(".")[0])
                except ValueError:
                    last_ci = None
            if last_ci and hasattr(last_ci, "date"):
                cc["days_inactive"] = (date.today() - last_ci.date()).days
            else:
                cc["days_inactive"] = 999
        else:
            cc["days_inactive"] = 999
    # Check if payments feature is enabled for this coach
    from tasks import _features_for as _ff
    coach_features = _ff(session["user_id"])
    payments_enabled = coach_features.get("payments", False)
    if payments_enabled:
        for cc in coachees:
            cc["payment"] = _payment_compliance(cc["id"])
        # Sort: compliant first (green < yellow < orange < red < none), then by name
        pay_order = {"green": 0, "yellow": 1, "orange": 2, "red": 3, "none": 4}
        coachees.sort(key=lambda x: (pay_order.get(x.get("payment", {}).get("status", "none"), 4), x.get("name", "")))
    else:
        for cc in coachees:
            cc["payment"] = {"status": "none"}
    # total ungraded for nav badge
    c.execute(
        """SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id
                 WHERE ce.coach_id=%s AND ta.status='completed' AND ta.grade IS NULL""",
        (session["user_id"],),
    )
    ungraded_total = c.fetchone()["cnt"]
    return render_template_string(_tpl("coach_dashboard.html"), coachees=coachees, ungraded_total=ungraded_total)



@bp.route("/coach/settings", methods=["GET", "POST"])
@login_required("coach")
def coach_settings():
    """Show/update coach account settings: password, display name, feature toggles.

    Route GET/POST /coach/settings — renders the coach settings screen (coach_settings.html).
    When: GET on settings load; POST on settings form submit (action=password|name|features).
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            c.execute("SELECT password_hash FROM coach WHERE id=%s", (session["user_id"],))
            row = c.fetchone()
            valid, _ = _verify_password(request.form["old_password"], row["password_hash"]) if row else (False, False)
            if valid:
                c.execute(
                    "UPDATE coach SET password_hash=%s WHERE id=%s",
                    (_hash_password(request.form["new_password"]), session["user_id"]),
                )
                _audit("change_password")
                flash("Password changed successfully.", "success")
            else:
                flash("Current password is incorrect.", "error")
        elif action == "name":
            new_name = request.form["name"].strip()
            if new_name:
                c.execute("UPDATE coach SET name=%s WHERE id=%s", (new_name, session["user_id"]))
                session["name"] = new_name
                flash("Name updated.", "success")
        elif action == "features":
            features = {k: k in request.form.getlist("features") for k, _ in FEATURES}
            c.execute("UPDATE coach SET features=%s WHERE id=%s", (json.dumps(features), session["user_id"]))
            flash("Features updated.", "success")
        return redirect(url_for("coach.coach_settings"))
    c.execute("SELECT name, features FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    coach_features = json.loads(coach["features"]) if coach["features"] and isinstance(coach["features"], str) else (coach["features"] if isinstance(coach["features"], dict) else {k: True for k, _ in FEATURES})
    return render_template_string(
        _tpl("coach_settings.html"), coach=coach, features=FEATURES, coach_features=coach_features
    )



@bp.route("/coach/change-password", methods=["POST"])
@login_required("coach")
def coach_change_password():
    """Verify the old password and set a new one for the logged-in coach.

    Route POST /coach/change-password — no screen; redirects to the coach settings screen.
    When: on password-change form submit (legacy endpoint alongside coach_settings action).
    """
    c = db()
    c.execute("SELECT password_hash FROM coach WHERE id=%s", (session["user_id"],))
    row = c.fetchone()
    valid, _ = _verify_password(request.form["old_password"], row["password_hash"]) if row else (False, False)
    if not valid:
        return redirect(url_for("coach.coach_settings"))
    c.execute(
        "UPDATE coach SET password_hash=%s WHERE id=%s", (_hash_password(request.form["new_password"]), session["user_id"])
    )
    _audit("change_password")
    return redirect(url_for("coach.coach_settings"))


@bp.route("/coach/change-name", methods=["POST"])
@login_required("coach")
def coach_change_name():
    """Update the coach's display name and session name.

    Route POST /coach/change-name — no screen; redirects to the coach branding screen.
    When: on name form submit from the branding screen (coach_branding.html).
    """
    c = db()
    new_name = request.form["name"].strip()
    if new_name:
        c.execute("UPDATE coach SET name=%s WHERE id=%s", (new_name, session["user_id"]))
        session["name"] = new_name
    return redirect(url_for("coach.coach_branding"))


@bp.route("/coach/support", methods=["GET", "POST"])
@login_required("coach")
def coach_support():
    """List the coach's support messages and let them file a new one (with recent audit trail).

    Route GET/POST /coach/support — renders the coach support screen (coach_support.html).
    When: GET on support screen load; POST on support-message form submit.
    """
    c = db()
    if request.method == "POST":
        c.execute(
            "SELECT action, created_at FROM audit_log WHERE user_id=%s AND role='coach' ORDER BY created_at DESC LIMIT 10",
            (session["user_id"],),
        )
        actions = c.fetchall()
        actions_text = "\n".join(f"[{a['created_at']}] {a['action']}" for a in actions)
        c.execute(
            "INSERT INTO support_message (coach_id, message, recent_actions) VALUES (%s,%s,%s)",
            (session["user_id"], request.form["message"], actions_text),
        )
        _audit("support_message")
        return redirect(url_for("coach.coach_support"))
    c.execute(
        "SELECT * FROM support_message WHERE coach_id=%s ORDER BY created_at DESC LIMIT 20", (session["user_id"],)
    )
    messages = c.fetchall()
    return render_template_string(_tpl("coach_support.html"), messages=messages)



@bp.route("/coach/branding", methods=["GET", "POST"])
@login_required("coach")
def coach_branding():
    """Show/save coach branding: logo upload, accent/bg/card colors, Telegram bot token.

    Route GET/POST /coach/branding — renders the coach branding screen (coach_branding.html).
    When: GET on branding screen load; POST on branding form submit.
    """
    c = db()
    if request.method == "POST":
        logo_path = None
        logo_data = request.form.get("logo_data")
        if logo_data and logo_data.startswith("data:image"):
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
            logo_path = f"{ATTACHMENTS_DIR}/logo_{session['user_id']}.png"
            with open(logo_path, "wb") as f:
                f.write(base64.b64decode(logo_data.split(",", 1)[1]))
        accent = request.form.get("accent_color", "#e94560")
        bg = request.form.get("bg_color", "#1a1a2e")
        card = request.form.get("card_color", "#16213e")
        tg_token = request.form.get("telegram_bot_token", "")
        if logo_path:
            c.execute(
                "UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s, logo_path=%s WHERE id=%s",
                (accent, bg, card, tg_token, logo_path, session["user_id"]),
            )
        else:
            c.execute(
                "UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s WHERE id=%s",
                (accent, bg, card, tg_token, session["user_id"]),
            )
        session.update(accent=accent, bg=bg, card=card)
        return redirect(url_for("coach.coach_branding"))
    c.execute(
        "SELECT accent_color, bg_color, card_color, telegram_bot_token, logo_path IS NOT NULL as has_logo FROM coach WHERE id=%s",
        (session["user_id"],),
    )
    coach = c.fetchone()
    return render_template_string(_tpl("coach_branding.html"), coach=coach)


@bp.route("/coach/logo")
def coach_logo():
    """Serve a coach's uploaded PNG logo (by ?id, or from session for coach/coachee).

    Route GET /coach/logo — no HTML screen; returns the image used across coach/coachee headers.
    When: on every page load that references the coach logo <img> src.
    """
    cid = request.args.get("id") or (
        session.get("coach_id") if session.get("role") == "coachee" else session.get("user_id")
    )
    if not cid:
        return "", 404
    c = db()
    c.execute("SELECT logo_path FROM coach WHERE id=%s", (cid,))
    row = c.fetchone()
    if not row or not row["logo_path"]:
        return "", 404
    try:
        with open(row["logo_path"], "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/png")
    except FileNotFoundError:
        return "", 404



@bp.route("/coach/coachee/add", methods=["GET", "POST"])
@login_required("coach")
def add_coachee():
    """Show the new-coachee form and create the coachee record under this coach.

    Route GET/POST /coach/coachee/add — renders the add-coachee screen (add_coachee.html);
    on success redirects to the coach dashboard.
    When: GET on form load; POST on add-coachee form submit.
    """
    if request.method == "POST":
        c = db()
        c.execute(
            """INSERT INTO coachee (username, password_hash, name, coach_id, contract_text, safe_word,
                     task_unveil_time, task_freeze_time, timezone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                request.form["username"],
                _hash_password(request.form["password"]),
                request.form["name"],
                session["user_id"],
                request.form.get("contract", ""),
                request.form.get("safe_word", "RED"),
                request.form.get("task_unveil_time", "08:00"),
                request.form.get("task_freeze_time", "22:00"),
                request.form.get("timezone", "Europe/London"),
            ),
        )
        return redirect(url_for("coach.coach_dashboard"))
    c = db()
    c.execute("SELECT timezone FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    return render_template_string(_tpl("add_coachee.html"), coach_tz=coach["timezone"] or "Europe/London")



@bp.route("/coach/coachee/<int:cid>")
@login_required("coach")
def coach_view_coachee(cid):
    """Aggregate a coachee's full record: tasks, check-ins, acks, tracking, notes, profile, goals, media, writing.

    Route GET /coach/coachee/<cid> — renders the detailed coachee screen (coach_view_coachee.html).
    When: on coachee detail-page load from the coach dashboard.
    """
    c = db()
    c.execute("SELECT * FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)
    # format timedelta TIME columns for HTML time inputs
    for k in ("task_unveil_time", "task_freeze_time"):
        v = coachee[k]
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            coachee[k] = f"{total//3600:02d}:{(total%3600)//60:02d}"
    c.execute(
        """SELECT ta.*, tt.title, tt.category FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s ORDER BY ta.created_at DESC LIMIT 20""",
        (cid,),
    )
    tasks = c.fetchall()
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    checkins = c.fetchall()
    c.execute("SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    acks = c.fetchall()
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    logs = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY pinned DESC, created_at DESC LIMIT 20", (cid,))
    notes = c.fetchall()
    c.execute(
        """SELECT mc.*, mcr.content as response, mcr.created_at as response_at
                 FROM mental_conditioning mc
                 LEFT JOIN mental_conditioning_response mcr ON mcr.conditioning_id=mc.id AND mcr.coachee_id=%s
                 WHERE mc.target='all' OR mc.coachee_id=%s
                 ORDER BY mc.prompt_date DESC LIMIT 20""",
        (cid, cid),
    )
    conditioning = c.fetchall()
    # psychological profile
    c.execute("SELECT profile_text FROM psychological_profile WHERE coachee_id=%s", (cid,))
    profile_row = c.fetchone()
    profile_text = profile_row["profile_text"] if profile_row else None
    c.execute("SELECT telegram_bot_token FROM coach WHERE id=%s", (session["user_id"],))
    tg_token = (c.fetchone() or {}).get("telegram_bot_token", "")
    c.execute("SELECT * FROM voice_note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    voice_notes = c.fetchall()
    c.execute("SELECT * FROM goal WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    goals = c.fetchall()
    c.execute(
        "SELECT * FROM journal WHERE coachee_id=%s AND visible_to_coach=1 ORDER BY created_at DESC LIMIT 10", (cid,)
    )
    journals = c.fetchall()
    c.execute("SELECT * FROM progress_photo WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    photos = c.fetchall()
    # Creative writing
    c.execute("SELECT COUNT(*) as cnt FROM creative_work WHERE coachee_id=%s", (cid,))
    writing_count = c.fetchone()["cnt"]
    c.execute(
        "SELECT COUNT(*) as cnt FROM creative_constraint WHERE coachee_id=%s AND used=0", (cid,)
    )
    writing_pending_constraints = c.fetchone()["cnt"]
    # Get all templates for the planning side panel
    c.execute("SELECT id, title, tags FROM task_template WHERE coach_id=%s ORDER BY title", (session["user_id"],))
    all_templates = c.fetchall()
    return render_template_string(
        _tpl("coach_view_coachee.html"),
        coachee=coachee,
        tasks=tasks,
        checkins=checkins,
        acks=acks,
        logs=logs,
        notes=notes,
        conditioning=conditioning,
        profile_text=profile_text,
        voice_notes=voice_notes,
        goals=goals,
        journals=journals,
        photos=photos,
        coachee_context=coachee.get("context_text", ""),
        completion_hours=_completion_hours(cid),
        all_templates=all_templates,
        llm_key=LLM_KEY,
        tg_token=tg_token or "",
        coach_tz=session.get("timezone", "Europe/London"),
        all_features=FEATURES,
        coachee_features=json.loads(coachee.get("features") or "null") if isinstance(coachee.get("features"), str) else (coachee.get("features") or {k: True for k, _ in FEATURES}),
        writing_count=writing_count,
        writing_pending_constraints=writing_pending_constraints,
    )



@bp.route("/coach/coachee/<int:cid>/edit", methods=["POST"])
@login_required("coach")
def edit_coachee(cid):
    """Update coachee settings (contract, safe word, times, timezone, avatar, features); versions changed contract.

    Route POST /coach/coachee/<cid>/edit — no screen; redirects to the coachee detail screen.
    When: on the edit-coachee form submit within coach_view_coachee.html.
    """
    c = db()
    new_contract = request.form.get("contract", "")
    # version contract if changed
    c.execute("SELECT contract_text FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    old = c.fetchone()
    if old and old["contract_text"] and old["contract_text"] != new_contract:
        c.execute(
            "INSERT INTO contract_history (coachee_id, contract_text) VALUES (%s,%s)", (cid, old["contract_text"])
        )
    coachee_features = {k: k in request.form.getlist("coachee_features") for k, _ in FEATURES}
    c.execute(
        """UPDATE coachee SET contract_text=%s, safe_word=%s, task_unveil_time=%s, task_freeze_time=%s,
                 timezone=%s, avatar=%s, color_scheme=%s, telegram_chat_id=%s, features=%s
                 WHERE id=%s AND coach_id=%s""",
        (
            new_contract,
            request.form.get("safe_word", "RED"),
            request.form.get("task_unveil_time", "08:00"),
            request.form.get("task_freeze_time", "22:00"),
            request.form.get("timezone", "Europe/London"),
            request.form.get("avatar", "\U0001f415"),
            request.form.get("color_scheme", "#e94560"),
            request.form.get("telegram_chat_id", ""),
            json.dumps(coachee_features),
            cid,
            session["user_id"],
        ),
    )
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/coachee/<int:cid>/context", methods=["POST"])
@login_required("coach")
def save_coachee_context(cid):
    """Save free-text coach context notes used to seed AI prompts for a coachee.

    Route POST /coach/coachee/<cid>/context — no screen; redirects to the coachee detail screen.
    When: on the context form submit within coach_view_coachee.html.
    """
    c = db()
    c.execute(
        "UPDATE coachee SET context_text=%s WHERE id=%s AND coach_id=%s",
        (request.form.get("context_text", ""), cid, session["user_id"]),
    )
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/coachee/<int:cid>/profile-prompt")
@login_required("coach")
def get_profile_prompt(cid):
    """Build and return (as JSON) the LLM prompt used for a coachee's psychological profile.

    Route GET /coach/coachee/<cid>/profile-prompt — JSON endpoint; no screen.
    When: fetched by client-side JS on the coachee detail screen before client-side AI generation.
    """
    prompt = _build_profile_prompt(cid)
    return json.dumps({"prompt": prompt}), 200, {"Content-Type": "application/json"}


@bp.route("/coach/coachee/<int:cid>/generate-profile", methods=["POST"])
@login_required("coach")
def generate_profile(cid):
    """Server-side AI profile generation via Cloudflare Workers AI; persists to psychological_profile.

    Route POST /coach/coachee/<cid>/generate-profile — JSON endpoint; no screen.
    When: on the "Generate profile" button click on the coachee detail screen.
    """
    prompt = _build_profile_prompt(cid)
    if not prompt:
        return json.dumps({"error": "No data to build profile"}), 400, {"Content-Type": "application/json"}
    result = _cf_ai_complete(prompt, max_tokens=1024)
    if result.startswith("[AI"):
        return json.dumps({"error": result}), 503, {"Content-Type": "application/json"}
    # Save to DB
    c = db()
    c.execute("SELECT id FROM psychological_profile WHERE coachee_id=%s", (cid,))
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE psychological_profile SET profile_text=%s, updated_at=CURRENT_TIMESTAMP WHERE coachee_id=%s",
            (result, cid),
        )
    else:
        c.execute("INSERT INTO psychological_profile (coachee_id, profile_text) VALUES (%s,%s)", (cid, result))
    return json.dumps({"text": result}), 200, {"Content-Type": "application/json"}



@bp.route("/coach/coachee/<int:cid>/profile", methods=["POST"])
@login_required("coach")
def save_profile(cid):
    """Upsert manually-edited psychological profile text for a coachee.

    Route POST /coach/coachee/<cid>/profile — JSON body; returns 204, no screen.
    When: on save of client-side-generated or hand-edited profile text on the coachee detail screen.
    """
    text_val = request.json.get("text", "") if request.is_json else ""
    if text_val:
        c = db()
        c.execute("SELECT id FROM psychological_profile WHERE coachee_id=%s", (cid,))
        existing = c.fetchone()
        if existing:
            c.execute(
                "UPDATE psychological_profile SET profile_text=%s, updated_at=CURRENT_TIMESTAMP WHERE coachee_id=%s",
                (text_val, cid),
            )
        else:
            c.execute("INSERT INTO psychological_profile (coachee_id, profile_text) VALUES (%s,%s)", (cid, text_val))
    return "", 204


@bp.route("/coach/analyze", methods=["GET", "POST"])
@login_required("coach")
def analyze_text():
    """Run an ad-hoc AI psychological analysis of pasted text (conversations, notes, journals).

    Route GET/POST /coach/analyze — GET renders the analyze screen (analyze.html);
    POST returns the AI result as JSON.
    When: GET on tool load; POST on analyze form/AJAX submit.
    """
    if request.method == "POST":
        input_text = ""
        if request.is_json:
            input_text = request.json.get("text", "")
        else:
            input_text = request.form.get("text", "")
        if not input_text:
            return json.dumps({"error": "No text provided"}), 400, {"Content-Type": "application/json"}
        coach_name = session.get("name", "Coach")
        prompt = (
            f"I am {coach_name}, a rather dominant coach. You are a coaching psychology assistant. "
            f"Analyze the following text \u2014 it could be a conversation, messages, journal entries, or session notes. "
            f"Provide a psychological profile of the person(s) involved: emotional patterns, communication style, "
            f"attachment tendencies, areas of strength, areas of concern, and any recommendations for a coach "
            f"working with them. Max 400 words. Be empathetic but honest.\n\nTEXT:\n{input_text[:15000]}"
        )
        result = _cf_ai_complete(prompt, max_tokens=1024)
        if result.startswith("[AI"):
            return json.dumps({"error": result}), 503, {"Content-Type": "application/json"}
        return json.dumps({"result": result}), 200, {"Content-Type": "application/json"}
    return render_template_string(_tpl("analyze.html"), llm_key=LLM_KEY, coach_name=session.get("name", "Coach"))



@bp.route("/coach/grading", methods=["GET", "POST"])
@login_required("coach")
def bulk_grading():
    """List all ungraded completed tasks for the coach and apply grades/comments in bulk.

    Route GET/POST /coach/grading — renders the bulk grading screen (bulk_grading.html).
    When: GET on grading screen load; POST on the bulk-grade form submit.
    """
    c = db()
    if request.method == "POST":
        for key, val in request.form.items():
            if key.startswith("grade_") and val:
                tid = int(key.split("_")[1])
                comment = request.form.get(f"comment_{tid}", "")
                c.execute(
                    """UPDATE task_assignment SET grade=%s, coach_comment=%s
                             WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
                    (val, comment, tid, session["user_id"]),
                )
        return redirect(url_for("coach.bulk_grading"))
    c.execute(
        """SELECT ta.id, ta.response, ta.responded_at, ta.grade, ta.coach_comment,
                        ta.attachment_path IS NOT NULL as has_attachment,
                        ta.photo_validation_result, ta.photo_validation_override,
                        tt.title, tt.category, ce.name as coachee_name
                 FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 JOIN coachee ce ON ta.coachee_id=ce.id
                 WHERE ce.coach_id=%s AND ta.status='completed' AND ta.grade IS NULL
                 ORDER BY ta.responded_at DESC""",
        (session["user_id"],),
    )
    tasks = c.fetchall()
    # Parse photo validation data for display
    for task in tasks:
        if task.get("photo_validation_result"):
            try:
                task["pv_result"] = json.loads(task["photo_validation_result"]) if isinstance(task["photo_validation_result"], str) else task["photo_validation_result"]
            except (json.JSONDecodeError, TypeError):
                task["pv_result"] = None
        else:
            task["pv_result"] = None
        if task.get("photo_validation_override"):
            try:
                task["pv_override"] = json.loads(task["photo_validation_override"]) if isinstance(task["photo_validation_override"], str) else task["photo_validation_override"]
            except (json.JSONDecodeError, TypeError):
                task["pv_override"] = None
        else:
            task["pv_override"] = None
    return render_template_string(_tpl("bulk_grading.html"), tasks=tasks)



@bp.route("/coach/tasks", methods=["GET", "POST"])
@login_required("coach")
def manage_tasks():
    """List task templates and coachees; create templates and assign tasks (incl. from library).

    Route GET/POST /coach/tasks — renders the task management screen (manage_tasks.html).
    When: GET on screen load; POST on create-template or assign_library form submit.
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "assign_library":
            tmpl_id = int(request.form["template_id"])
            coachee_ids = request.form.getlist("coachee_ids")
            due = request.form.get("due_date") or None
            for cid_str in coachee_ids:
                cid = int(cid_str)
                c.execute("SELECT task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (cid,))
                cc = c.fetchone()
                d = due or date.today().isoformat()
                vis = f"{d} {cc['task_unveil_time']}" if cc and cc["task_unveil_time"] else None
                frz = f"{d} {cc['task_freeze_time']}" if cc and cc["task_freeze_time"] else None
                c.execute(
                    "INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                    (tmpl_id, cid, d, vis, frz),
                )
            return redirect(url_for("coach.manage_tasks"))
        # create new
        is_reserve = 1 if request.form.get("is_reserve") else 0
        in_library = 1 if request.form.get("in_library") else 0
        auto_grade = 1 if request.form.get("auto_grade") else 0
        photo_validate = 1 if request.form.get("photo_validate") else 0
        tags = request.form.get("tags", "").strip()
        recur_days = int(request.form.get("recur_days") or 0) or None
        recur_approx = 1 if request.form.get("recur_approx") else 0
        c.execute(
            """INSERT INTO task_template (coach_id, title, description, recurrence, category, difficulty, is_reserve, recur_days, recur_approx, in_library, auto_grade, photo_validate, tags)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                session["user_id"],
                request.form["title"],
                request.form["description"],
                request.form["recurrence"],
                request.form["category"],
                request.form.get("difficulty", "medium"),
                is_reserve,
                recur_days,
                recur_approx,
                in_library,
                auto_grade,
                photo_validate,
                tags or None,
            ),
        )
        tmpl_id = c.lastrowid
        if not tmpl_id:
            c.execute("SELECT MAX(id) as mid FROM task_template WHERE coach_id=%s", (session["user_id"],))
            tmpl_id = c.fetchone()["mid"]
        if not is_reserve:
            coachee_ids = request.form.getlist("coachee_ids")
            due = request.form.get("due_date") or None
            for cid_str in coachee_ids:
                cid = int(cid_str)
                c.execute("SELECT task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (cid,))
                cc = c.fetchone()
                today = date.today().isoformat()
                vis = f"{today} {cc['task_unveil_time']}" if cc and cc["task_unveil_time"] else None
                frz = f"{today} {cc['task_freeze_time']}" if cc and cc["task_freeze_time"] else None
                if due:
                    vis = f"{due} {cc['task_unveil_time']}" if cc and cc["task_unveil_time"] else None
                    frz = f"{due} {cc['task_freeze_time']}" if cc and cc["task_freeze_time"] else None
                c.execute(
                    "INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                    (tmpl_id, cid, due or today, vis, frz),
                )
        return redirect(url_for("coach.manage_tasks"))
    c.execute("SELECT * FROM task_template WHERE coach_id=%s ORDER BY created_at DESC", (session["user_id"],))
    templates = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s ORDER BY name", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("manage_tasks.html"), templates=templates, coachees=coachees)



@bp.route("/coach/library-search")
@login_required("coach")
def library_search():
    """Return library task templates with per-coachee usage counts/last-used as JSON.

    Route GET /coach/library-search — JSON endpoint; no screen.
    When: fetched by JS on the task management screen (manage_tasks.html) when browsing the library.
    """
    c = db()
    c.execute(
        "SELECT id, title, description, category FROM task_template WHERE coach_id=%s AND in_library=1 ORDER BY title",
        (session["user_id"],),
    )
    templates = c.fetchall()
    for t in templates:
        c.execute(
            """SELECT ce.id, ce.name, COUNT(ta.id) as times, MAX(ta.due_date) as last_date
                     FROM coachee ce LEFT JOIN task_assignment ta ON ta.coachee_id=ce.id AND ta.template_id=%s
                     WHERE ce.coach_id=%s GROUP BY ce.id, ce.name ORDER BY ce.name""",
            (t["id"], session["user_id"]),
        )
        t["usage"] = {
            str(r["id"]): {"times": r["times"], "last": str(r["last_date"]) if r["last_date"] else None}
            for r in c.fetchall()
        }
    return json.dumps([dict(t) for t in templates], default=str), 200, {"Content-Type": "application/json"}


@bp.route("/coach/conditioning", methods=["GET", "POST"])
@login_required("coach")
def manage_conditioning():
    """List recent mental-conditioning prompts and create new ones (shared or per-coachee).

    Route GET/POST /coach/conditioning — renders the conditioning screen (manage_conditioning.html).
    When: GET on screen load; POST on the new-prompt form submit.
    """
    c = db()
    if request.method == "POST":
        target = request.form["target"]
        coachee_id = request.form.get("coachee_id") if target == "individual" else None
        c.execute(
            "INSERT INTO mental_conditioning (coach_id, prompt_date, prompt_text, target, coachee_id) VALUES (%s,%s,%s,%s,%s)",
            (
                session["user_id"],
                request.form.get("prompt_date", date.today().isoformat()),
                request.form["prompt_text"],
                target,
                coachee_id,
            ),
        )
        return redirect(url_for("coach.manage_conditioning"))
    c.execute(
        """SELECT mc.*, co.name as coachee_name FROM mental_conditioning mc
                 LEFT JOIN coachee co ON mc.coachee_id=co.id
                 WHERE mc.coach_id=%s ORDER BY prompt_date DESC LIMIT 30""",
        (session["user_id"],),
    )
    prompts = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("manage_conditioning.html"), prompts=prompts, coachees=coachees)



@bp.route("/coach/ack/<int:cid>", methods=["POST"])
@login_required("coach")
def give_acknowledgement(cid):
    """Record a positive/negative acknowledgement for a coachee.

    Route POST /coach/ack/<cid> — no screen; redirects to the coachee detail screen.
    When: on the acknowledgement form submit within coach_view_coachee.html.
    """
    c = db()
    c.execute(
        "INSERT INTO acknowledgement (coachee_id, coach_id, ack_type, description, notes) VALUES (%s,%s,%s,%s,%s)",
        (cid, session["user_id"], request.form["ack_type"], request.form["description"], request.form.get("notes", "")),
    )
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/task/<int:tid>/review", methods=["POST"])
@login_required("coach")
def review_task(tid):
    """Set a grade and coach comment on a single completed task assignment.

    Route POST /coach/task/<tid>/review — no screen; redirects to the coachee detail screen.
    When: on the per-task review form submit within coach_view_coachee.html.
    """
    c = db()
    c.execute(
        """UPDATE task_assignment SET grade=%s, coach_comment=%s
                 WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
        (request.form.get("grade"), request.form.get("coach_comment", ""), tid, session["user_id"]),
    )
    cid = request.form.get("coachee_id")
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/note/<int:cid>", methods=["POST"])
@login_required("coach")
def coach_add_note(cid):
    """Post a coach note to a coachee, optionally scheduled for later delivery.

    Route POST /coach/note/<cid> — no screen; redirects to the coachee detail screen.
    When: on the add-note form submit within coach_view_coachee.html.
    """
    c = db()
    scheduled = request.form.get("scheduled_at") or None
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content, scheduled_at) VALUES (%s,'coach',%s,%s)",
        (cid, request.form["content"], scheduled),
    )
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/note/<int:nid>/pin", methods=["POST"])
@login_required("coach")
def pin_note(nid):
    """Toggle the pinned flag on a note owned by one of the coach's coachees.

    Route POST /coach/note/<nid>/pin — no screen; redirects back (referrer or coach dashboard).
    When: on the pin/unpin button submit from the coachee detail screen.
    """
    c = db()
    c.execute(
        "UPDATE note SET pinned=CASE WHEN pinned=0 THEN 1 ELSE 0 END WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)",
        (nid, session["user_id"]),
    )
    return redirect(request.referrer or url_for("coach.coach_dashboard"))


@bp.route("/coach/quick-note/<int:cid>", methods=["POST"])
@login_required("coach")
def quick_note(cid):
    """Post a quick coach note to a coachee from the dashboard.

    Route POST /coach/quick-note/<cid> — no screen; redirects to the coach dashboard.
    When: on the quick-note inline form submit on the coach dashboard (coach_dashboard.html).
    """
    c = db()
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)", (cid, request.form["content"])
    )
    return redirect(url_for("coach.coach_dashboard"))


@bp.route("/coach/quick-ack/<int:cid>", methods=["POST"])
@login_required("coach")
def quick_ack(cid):
    """Record a quick acknowledgement for a coachee from the dashboard.

    Route POST /coach/quick-ack/<cid> — no screen; redirects to the coach dashboard.
    When: on the quick-ack inline form submit on the coach dashboard (coach_dashboard.html).
    """
    c = db()
    c.execute(
        "INSERT INTO acknowledgement (coachee_id, coach_id, ack_type, description) VALUES (%s,%s,%s,%s)",
        (cid, session["user_id"], request.form["ack_type"], request.form["description"]),
    )
    return redirect(url_for("coach.coach_dashboard"))



@bp.route("/coach/audit")
@login_required("coach")
def audit_log():
    """List the 100 most recent audit-log entries.

    Route GET /coach/audit — renders the audit log screen (audit_log.html).
    When: on audit-log screen load from the coach navigation.
    """
    c = db()
    c.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100")
    logs = c.fetchall()
    return render_template_string(_tpl("audit_log.html"), logs=logs)


@bp.route("/coach/coachee/<int:cid>/contracts")
@login_required("coach")
def contract_history(cid):
    """List versioned contract snapshots for a coachee.

    Route GET /coach/coachee/<cid>/contracts — renders the contract history screen (contract_history.html).
    When: on contract-history screen load from the coachee detail screen.
    """
    c = db()
    c.execute("SELECT * FROM contract_history WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    history = c.fetchall()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    return render_template_string(_tpl("contract_history.html"), history=history, coachee=coachee)


@bp.route("/coach/coachee/<int:cid>/summary")
@login_required("coach")
def weekly_summary(cid):
    """Compute this week's stats for a coachee (tasks, grades, missed, check-ins, streaks).

    Route GET /coach/coachee/<cid>/summary — renders the weekly summary screen (weekly_summary.html).
    When: on weekly-summary screen load from the coachee detail screen.
    """
    c = db()
    c.execute("SELECT name, timezone FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)
    tz = ZoneInfo(coachee["timezone"] or "UTC")
    today = datetime.now(tz).date()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end = today.isoformat()
    c.execute(
        "SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s",
        (cid, week_start, week_end),
    )
    total = c.fetchone()["n"]
    c.execute(
        "SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND status='completed'",
        (cid, week_start, week_end),
    )
    completed = c.fetchone()["n"]
    c.execute(
        "SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND status='missed'",
        (cid, week_start, week_end),
    )
    missed = c.fetchone()["n"]
    c.execute(
        "SELECT AVG(CASE grade WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6 END) as avg_g FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND grade IS NOT NULL",
        (cid, week_start, week_end),
    )
    avg = c.fetchone()["avg_g"]
    avg_grade = chr(64 + round(avg)) if avg else "\u2014"
    c.execute(
        "SELECT COUNT(*) as n FROM checkin WHERE coachee_id=%s AND DATE(created_at) BETWEEN %s AND %s",
        (cid, week_start, week_end),
    )
    checkins = c.fetchone()["n"]
    c.execute("SELECT current_streak, best_streak, strikes FROM coachee WHERE id=%s", (cid,))
    streaks = c.fetchone()
    summary = {
        "week_start": week_start,
        "week_end": week_end,
        "total": total,
        "completed": completed,
        "missed": missed,
        "avg_grade": avg_grade,
        "checkins": checkins,
        **streaks,
    }
    return render_template_string(_tpl("weekly_summary.html"), coachee=coachee, s=summary)



@bp.route("/coach/coachee/<int:cid>/reset-password", methods=["POST"])
@login_required("coach")
def reset_coachee_password(cid):
    """Set a new password for one of the coach's coachees (audited).

    Route POST /coach/coachee/<cid>/reset-password — no screen; redirects to the coachee detail screen.
    When: on the reset-password form submit within coach_view_coachee.html.
    """
    c = db()
    new_pw = request.form["new_password"]
    c.execute(
        "UPDATE coachee SET password_hash=%s WHERE id=%s AND coach_id=%s", (_hash_password(new_pw), cid, session["user_id"])
    )
    _audit(f"reset_password coachee={cid}")
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/template/<int:tid>/edit", methods=["POST"])
@login_required("coach")
def edit_template(tid):
    """Update fields of an existing task template owned by the coach.

    Route POST /coach/template/<tid>/edit — no screen; redirects to the task management screen.
    When: on the edit-template form submit within manage_tasks.html.
    """
    c = db()
    c.execute(
        """UPDATE task_template SET title=%s, description=%s, category=%s, difficulty=%s,
                 recur_days=%s, recur_approx=%s, in_library=%s, auto_grade=%s, photo_validate=%s, tags=%s
                 WHERE id=%s AND coach_id=%s""",
        (
            request.form["title"],
            request.form.get("description", ""),
            request.form.get("category", "mental"),
            request.form.get("difficulty", "medium"),
            int(request.form.get("recur_days") or 0) or None,
            1 if request.form.get("recur_approx") else 0,
            1 if request.form.get("in_library") else 0,
            1 if request.form.get("auto_grade") else 0,
            1 if request.form.get("photo_validate") else 0,
            request.form.get("tags", "").strip() or None,
            tid,
            session["user_id"],
        ),
    )
    return redirect(url_for("coach.manage_tasks"))


@bp.route("/coach/template/<int:tid>/delete", methods=["POST"])
@login_required("coach")
def delete_template(tid):
    """Delete a task template owned by the coach.

    Route POST /coach/template/<tid>/delete — no screen; redirects to the task management screen.
    When: on the delete-template button submit within manage_tasks.html.
    """
    c = db()
    c.execute("DELETE FROM task_template WHERE id=%s AND coach_id=%s", (tid, session["user_id"]))
    return redirect(url_for("coach.manage_tasks"))


@bp.route("/coach/voice/<int:cid>", methods=["POST"])
@login_required("coach")
def coach_voice_note(cid):
    """Save a coach-recorded audio (webm) message for a coachee to disk and DB.

    Route POST /coach/voice/<cid> — no screen; redirects to the coachee detail screen.
    When: on the voice-note recorder submit within coach_view_coachee.html.
    """
    c = db()
    audio = request.form.get("audio_data")
    if audio and audio.startswith("data:audio"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/voice_{cid}_{int(utcnow().timestamp())}.webm"
        with open(path, "wb") as f:
            f.write(base64.b64decode(audio.split(",", 1)[1]))
        dur = int(request.form.get("duration", 0))
        c.execute(
            "INSERT INTO voice_note (coachee_id, author_role, file_path, duration_sec) VALUES (%s,'coach',%s,%s)",
            (cid, path, dur),
        )
    return redirect(url_for("coach.coach_view_coachee", cid=cid))



@bp.route("/coach/goal/<int:gid>", methods=["POST"])
@login_required("coach")
def review_goal(gid):
    """Approve/reject a coachee-proposed goal and attach coach notes.

    Route POST /coach/goal/<gid> — no screen; redirects back (referrer or coach dashboard).
    When: on the goal-review form submit from the coachee detail screen.
    """
    c = db()
    c.execute(
        """UPDATE goal SET status=%s, coach_notes=%s
                 WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
        (request.form["status"], request.form.get("coach_notes", ""), gid, session["user_id"]),
    )
    return redirect(request.referrer or url_for("coach.coach_dashboard"))


@bp.route("/coach/coachee/<int:cid>/heatmap")
@login_required("coach")
def compliance_heatmap(cid):
    """Build a 90-day per-day task compliance map (total/completed/missed) for a coachee.

    Route GET /coach/coachee/<cid>/heatmap — renders the heatmap screen (heatmap.html).
    When: on heatmap screen load from the coachee detail screen.
    """
    c = db()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)
    ninety_days_ago = (date.today() - timedelta(days=90)).isoformat()
    c.execute(
        """SELECT due_date, status FROM task_assignment WHERE coachee_id=%s AND due_date IS NOT NULL
                 AND due_date >= %s ORDER BY due_date""",
        (cid, ninety_days_ago),
    )
    tasks = c.fetchall()
    days = {}
    for t in tasks:
        d = str(t["due_date"])
        if d not in days:
            days[d] = {"total": 0, "completed": 0, "missed": 0}
        days[d]["total"] += 1
        if t["status"] == "completed":
            days[d]["completed"] += 1
        elif t["status"] == "missed":
            days[d]["missed"] += 1
    return render_template_string(_tpl("heatmap.html"), coachee=coachee, days=json.dumps(days), cid=cid)


@bp.route("/coach/coachee/<int:cid>/categories")
@login_required("coach")
def category_breakdown(cid):
    """Aggregate task totals, completion/missed counts, and average grade per category for a coachee.

    Route GET /coach/coachee/<cid>/categories — renders the category breakdown screen (categories.html).
    When: on category-breakdown screen load from the coachee detail screen.
    """
    c = db()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    c.execute(
        """SELECT tt.category, COUNT(*) as total,
                 SUM(CASE WHEN ta.status='completed' THEN 1 ELSE 0 END) as completed,
                 SUM(CASE WHEN ta.status='missed' THEN 1 ELSE 0 END) as missed,
                 AVG(CASE ta.grade WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6 END) as avg_g
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s GROUP BY tt.category""",
        (cid,),
    )
    cats = c.fetchall()
    for cat in cats:
        cat["avg_grade"] = chr(64 + round(cat["avg_g"])) if cat["avg_g"] else "\u2014"
    return render_template_string(_tpl("categories.html"), coachee=coachee, cats=cats)



@bp.route("/coach/automations", methods=["GET", "POST"])
@login_required("coach")
def manage_automations():
    """List and manage coach automation rules (create/delete/toggle trigger→condition→action).

    Route GET/POST /coach/automations — renders the automations screen (manage_automations.html).
    When: GET on screen load; POST on the create/delete/toggle rule form submit.
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            c.execute(
                """INSERT INTO auto_rule (coach_id, name, trigger, condition_field, condition_op, condition_value, action_type, action_template)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    session["user_id"],
                    request.form["name"],
                    request.form["trigger"],
                    request.form.get("condition_field") or None,
                    request.form.get("condition_op") or None,
                    request.form.get("condition_value") or None,
                    request.form["action_type"],
                    request.form["action_template"],
                ),
            )
            flash("Automation rule created.", "success")
        elif action == "delete":
            c.execute("DELETE FROM auto_rule WHERE id=%s AND coach_id=%s", (request.form["rule_id"], session["user_id"]))
            flash("Rule deleted.", "success")
        elif action == "toggle":
            c.execute(
                "UPDATE auto_rule SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=%s AND coach_id=%s",
                (request.form["rule_id"], session["user_id"]),
            )
        return redirect(url_for("coach.manage_automations"))
    c.execute("SELECT * FROM auto_rule WHERE coach_id=%s ORDER BY active DESC, created_at DESC", (session["user_id"],))
    rules = c.fetchall()
    return render_template_string(_tpl("manage_automations.html"), rules=rules)



@bp.route("/coach/rituals", methods=["GET", "POST"])
@login_required("coach")
def manage_rituals():
    """List and manage recurring ritual definitions (create/delete, shared or per-coachee).

    Route GET/POST /coach/rituals — renders the rituals screen (manage_rituals.html).
    When: GET on screen load; POST on the create/delete ritual form submit.
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            coachee_id = request.form.get("coachee_id") or None
            c.execute(
                "INSERT INTO ritual (coach_id, coachee_id, name, description, schedule, schedule_days) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    session["user_id"],
                    coachee_id,
                    request.form["name"],
                    request.form.get("description", ""),
                    request.form.get("schedule", "daily"),
                    request.form.get("schedule_days", ""),
                ),
            )
            flash("Ritual created.", "success")
        elif action == "delete":
            rid = request.form.get("ritual_id")
            c.execute("DELETE FROM ritual WHERE id=%s AND coach_id=%s", (rid, session["user_id"]))
            flash("Ritual deleted.", "success")
        return redirect(url_for("coach.manage_rituals"))
    c.execute("SELECT r.*, co.name as coachee_name FROM ritual r LEFT JOIN coachee co ON r.coachee_id=co.id WHERE r.coach_id=%s ORDER BY r.active DESC, r.name", (session["user_id"],))
    rituals = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("manage_rituals.html"), rituals=rituals, coachees=coachees)


@bp.route("/coach/badge/<int:cid>", methods=["POST"])
@login_required("coach")
def award_badge(cid):
    """Coach manually awards a gamification badge to a coachee.

    Route POST /coach/badge/<cid> — no screen; redirects to the coachee detail screen.
    When: on the award-badge form submit within coach_view_coachee.html.
    """
    c = db()
    c.execute(
        "INSERT INTO badge (coachee_id, badge_type, badge_name, description, icon) VALUES (%s,%s,%s,%s,%s)",
        (cid, "manual_" + str(int(utcnow().timestamp())), request.form["badge_name"], request.form.get("description", ""), request.form.get("icon", "\U0001f3c6")),
    )
    flash("Badge awarded.", "success")
    return redirect(url_for("coach.coach_view_coachee", cid=cid))



@bp.route("/coach/coachee/<int:cid>/ai-digest", methods=["POST"])
@login_required("coach")
def ai_weekly_digest(cid):
    """Generate an AI weekly digest for a coachee and persist it to weekly_summary.

    Route POST /coach/coachee/<cid>/ai-digest — JSON endpoint; no screen.
    When: on the "AI weekly digest" button click on the coachee detail screen.
    """
    c = db()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee_row = c.fetchone()
    if not coachee_row:
        return json.dumps({"error": "Coachee not found"}), 404, {"Content-Type": "application/json"}
    name = coachee_row["name"]

    c.execute("SELECT checkin_type, content, created_at FROM checkin WHERE coachee_id=%s AND DATE(created_at) >= %s ORDER BY created_at", (cid, week_ago))
    checkins = c.fetchall()
    c.execute("SELECT tt.title, ta.status, ta.grade, ta.response FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id WHERE ta.coachee_id=%s AND ta.due_date >= %s", (cid, week_ago))
    tasks = c.fetchall()
    c.execute("SELECT category, content FROM tracking_log WHERE coachee_id=%s AND DATE(created_at) >= %s", (cid, week_ago))
    tracking = c.fetchall()

    report = _weekly_report(cid)

    dash = "\u2014"
    nl = "\n"
    checkins_text = nl.join(f"  [{c_['checkin_type']}] {str(c_['content'])[:200]}" for c_ in checkins[:10])
    tasks_text = nl.join(f"  {t['title']}: {t['status']} (grade: {t.get('grade', dash)})" for t in tasks[:10])
    tracking_text = nl.join(f"  [{t['category']}] {str(t['content'])[:100]}" for t in tracking[:10])

    prompt = f"""You are a coaching assistant. Write a concise weekly digest (max 250 words) for a coach about their coachee "{name}". Summarize the week factually and highlight patterns, concerns, and wins.

STATS: Grade avg {report['avg_grade']}, Compliance {report['compliance']}%, Check-in rate {report['checkin_rate']}%, {report['tracking_count']} tracking entries.

CHECK-INS ({len(checkins)} this week):
{checkins_text}

TASKS ({len(tasks)} assigned):
{tasks_text}

TRACKING:
{tracking_text}

Write a professional summary identifying: 1) Key wins 2) Areas of concern 3) Suggested focus for next week."""

    result = _cf_ai_complete(prompt, max_tokens=800)
    if result.startswith("[AI"):
        return json.dumps({"error": result}), 503, {"Content-Type": "application/json"}

    # Save to weekly_summary
    week_start = week_ago
    c.execute("SELECT id FROM weekly_summary WHERE coachee_id=%s AND week_start=%s", (cid, week_start))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE weekly_summary SET summary_text=%s WHERE id=%s", (result, existing["id"]))
    else:
        c.execute("INSERT INTO weekly_summary (coachee_id, week_start, summary_text) VALUES (%s,%s,%s)", (cid, week_start, result))

    return json.dumps({"text": result}), 200, {"Content-Type": "application/json"}



@bp.route("/coach/nudge/<int:cid>", methods=["POST"])
@login_required("coach")
def nudge_coachee(cid):
    """Send a nudge note (merge-var templated) to an inactive coachee.

    Route POST /coach/nudge/<cid> — no screen; redirects to the coach dashboard.
    When: on the nudge button submit for inactive coachees on the coach dashboard.
    """
    c = db()
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)
    template = request.form.get("content", "").strip()
    if not template:
        template = "Hey {{name}}, I noticed you've been quiet. Everything okay? Remember: consistency beats perfection. Even a small check-in counts. I'm here when you're ready."
    text = _merge_vars(template, cid)
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
        (cid, text),
    )
    flash(f"Nudge sent.", "success")
    return redirect(url_for("coach.coach_dashboard"))


@bp.route("/coach/conditioning/generate/<int:cid>", methods=["POST"])
@login_required("coach")
def generate_conditioning(cid):
    """AI-generate a daily conditioning prompt for a coachee and save it as today's prompt.

    Route POST /coach/conditioning/generate/<cid> — JSON endpoint; no screen.
    When: on the "Generate conditioning" button click on the coachee detail screen.
    """
    c = db()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee_row = c.fetchone()
    if not coachee_row:
        return json.dumps({"error": "Coachee not found"}), 404, {"Content-Type": "application/json"}
    name = coachee_row["name"]

    # Get recent context for prompt generation
    c.execute("SELECT content FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 5", (cid,))
    recent_checkins = [r["content"][:200] for r in c.fetchall()]
    c.execute("SELECT content FROM mental_conditioning_response WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 3", (cid,))
    recent_responses = [r["content"][:200] for r in c.fetchall()]

    from merge import _get_merge_context
    ctx = _get_merge_context(cid)

    prompt = f"""You are a dominant coach writing a daily mental conditioning prompt for your submissive coachee "{name}". 
Their stats: streak {ctx['streak']} days, level {ctx['level']}, grade avg {ctx['grade_avg']}, {ctx['days_active']} days active, {ctx['strikes']} strikes.

Recent check-ins: {'; '.join(recent_checkins[:3]) if recent_checkins else 'None yet'}
Recent conditioning responses: {'; '.join(recent_responses[:2]) if recent_responses else 'None yet'}

Write ONE conditioning prompt (2-4 sentences). It should be thought-provoking, push their growth edge, and reinforce the dynamic. Address them by name. Do NOT explain what you're doing — just write the prompt itself."""

    result = _cf_ai_complete(prompt, max_tokens=300)
    if result.startswith("[AI"):
        return json.dumps({"error": result}), 503, {"Content-Type": "application/json"}

    # Save as today's conditioning prompt
    today = date.today().isoformat()
    c.execute(
        "INSERT INTO mental_conditioning (coach_id, prompt_date, prompt_text, target, coachee_id) VALUES (%s,%s,%s,'specific',%s)",
        (session["user_id"], today, result.strip(), cid),
    )
    return json.dumps({"text": result.strip()}), 200, {"Content-Type": "application/json"}


@bp.route("/coach/week-plan", methods=["GET", "POST"])
@login_required("coach")
def manage_week_plan():
    """Manage the weekly recurring task plan (add/delete day→template entries).

    Route GET/POST /coach/week-plan — renders the week plan screen (week_plan.html).
    When: GET on screen load; POST on the add/delete plan-entry form submit.
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            day = int(request.form["day_of_week"])
            tmpl_id = int(request.form["template_id"])
            coachee_id = request.form.get("coachee_id") or None
            c.execute(
                "INSERT INTO week_plan (coach_id, day_of_week, template_id, coachee_id) VALUES (%s,%s,%s,%s)",
                (session["user_id"], day, tmpl_id, coachee_id),
            )
            flash("Plan entry added.", "success")
        elif action == "delete":
            c.execute("DELETE FROM week_plan WHERE id=%s AND coach_id=%s", (request.form["plan_id"], session["user_id"]))
            flash("Entry removed.", "success")
        return redirect(url_for("coach.manage_week_plan"))

    c.execute(
        """SELECT wp.*, tt.title as task_title, co.name as coachee_name
           FROM week_plan wp
           JOIN task_template tt ON wp.template_id=tt.id
           LEFT JOIN coachee co ON wp.coachee_id=co.id
           WHERE wp.coach_id=%s ORDER BY wp.day_of_week""",
        (session["user_id"],),
    )
    plan = c.fetchall()
    c.execute("SELECT id, title FROM task_template WHERE coach_id=%s ORDER BY title", (session["user_id"],))
    templates = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("week_plan.html"), plan=plan, templates=templates, coachees=coachees)


@bp.route("/coach/onboarding", methods=["GET", "POST"])
@login_required("coach")
def manage_onboarding():
    """Manage the scripted onboarding sequence for new coachees (add/delete day-offset steps).

    Route GET/POST /coach/onboarding — renders the onboarding screen (onboarding.html).
    When: GET on screen load; POST on the add/delete onboarding-step form submit.
    """
    c = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            day_offset = int(request.form["day_offset"])
            tmpl_id = request.form.get("template_id") or None
            note_text = request.form.get("note_text") or None
            if tmpl_id:
                tmpl_id = int(tmpl_id)
            c.execute(
                "INSERT INTO onboarding_step (coach_id, day_offset, template_id, note_text) VALUES (%s,%s,%s,%s)",
                (session["user_id"], day_offset, tmpl_id, note_text),
            )
            flash("Onboarding step added.", "success")
        elif action == "delete":
            c.execute("DELETE FROM onboarding_step WHERE id=%s AND coach_id=%s", (request.form["step_id"], session["user_id"]))
            flash("Step removed.", "success")
        return redirect(url_for("coach.manage_onboarding"))

    c.execute(
        """SELECT os.*, tt.title as task_title
           FROM onboarding_step os
           LEFT JOIN task_template tt ON os.template_id=tt.id
           WHERE os.coach_id=%s ORDER BY os.day_offset""",
        (session["user_id"],),
    )
    steps = c.fetchall()
    c.execute("SELECT id, title FROM task_template WHERE coach_id=%s ORDER BY title", (session["user_id"],))
    templates = c.fetchall()
    return render_template_string(_tpl("onboarding.html"), steps=steps, templates=templates)



@bp.route("/coach/coachee/<int:cid>/task-context/<int:tid>")
@login_required("coach")
def task_context(cid, tid):
    """Return coachee-specific history for a task template (last assigned, count, grades, last response) as JSON.

    Route GET /coach/coachee/<cid>/task-context/<tid> — JSON endpoint; no screen.
    When: fetched by JS on the coachee detail screen's task-planning panel when hovering/selecting a template.
    """
    c = db()
    # Verify ownership
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)

    # Template info
    c.execute("SELECT title, recur_days, recur_approx, category, difficulty, tags FROM task_template WHERE id=%s AND coach_id=%s", (tid, session["user_id"]))
    tmpl = c.fetchone()
    if not tmpl:
        abort(404)

    # Last assigned date
    c.execute(
        "SELECT due_date FROM task_assignment WHERE template_id=%s AND coachee_id=%s ORDER BY due_date DESC LIMIT 1",
        (tid, cid),
    )
    last_row = c.fetchone()
    last_assigned = str(last_row["due_date"]) if last_row else None

    # Total times assigned
    c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE template_id=%s AND coachee_id=%s", (tid, cid))
    total_assigned = c.fetchone()["cnt"]

    # Grade history (last 5)
    c.execute(
        "SELECT grade, due_date, responded_at FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND grade IS NOT NULL ORDER BY due_date DESC LIMIT 5",
        (tid, cid),
    )
    grade_history = [{"grade": r["grade"], "date": str(r["due_date"]), "responded": str(r["responded_at"]) if r["responded_at"] else None} for r in c.fetchall()]

    # Average grade for this task
    c.execute(
        "SELECT AVG(CASE grade WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6 END) as avg_g FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND grade IS NOT NULL",
        (tid, cid),
    )
    avg_row = c.fetchone()
    avg_grade = chr(64 + round(avg_row["avg_g"])) if avg_row and avg_row["avg_g"] else None

    # Last response
    c.execute(
        "SELECT response, grade, coach_comment, responded_at FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND response IS NOT NULL ORDER BY due_date DESC LIMIT 1",
        (tid, cid),
    )
    last_resp_row = c.fetchone()
    last_response = None
    if last_resp_row:
        resp_text = last_resp_row["response"] or ""
        last_response = {
            "text": resp_text[:300] + ("..." if len(resp_text) > 300 else ""),
            "grade": last_resp_row["grade"],
            "comment": last_resp_row["coach_comment"],
            "date": str(last_resp_row["responded_at"]) if last_resp_row["responded_at"] else None,
        }

    result = {
        "template": {
            "title": tmpl["title"],
            "recur_days": tmpl["recur_days"],
            "recur_approx": bool(tmpl["recur_approx"]),
            "category": tmpl["category"],
            "difficulty": tmpl["difficulty"],
            "tags": tmpl["tags"],
        },
        "last_assigned": last_assigned,
        "total_assigned": total_assigned,
        "avg_grade": avg_grade,
        "grade_history": grade_history,
        "last_response": last_response,
    }
    return json.dumps(result), 200, {"Content-Type": "application/json"}



@bp.route("/coach/coachee/<int:cid>/payments", methods=["GET", "POST"])
@login_required("coach")
def coachee_payments(cid):
    """View/manage a coachee's payments: confirm payments, set up/deactivate a plan, show compliance.

    Route GET/POST /coach/coachee/<cid>/payments — renders the payments screen (payments.html).
    When: GET on screen load; POST on confirm_payment / setup_plan / deactivate_plan form submit.
    """
    c = db()
    c.execute("SELECT id, name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "confirm_payment":
            c.execute(
                "INSERT INTO payment_log (coachee_id, amount, currency, period_start, period_end, notes) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    cid,
                    request.form["amount"],
                    request.form.get("currency", "EUR"),
                    request.form.get("period_start") or None,
                    request.form.get("period_end") or None,
                    request.form.get("notes", ""),
                ),
            )
            flash("Payment confirmed.", "success")
        elif action == "setup_plan":
            # Check if plan exists
            c.execute("SELECT id FROM payment_plan WHERE coachee_id=%s", (cid,))
            existing = c.fetchone()
            if existing:
                c.execute(
                    "UPDATE payment_plan SET frequency=%s, amount=%s, currency=%s, start_date=%s, active=1 WHERE coachee_id=%s",
                    (
                        request.form["frequency"],
                        request.form["plan_amount"],
                        request.form.get("currency", "EUR"),
                        request.form["start_date"],
                        cid,
                    ),
                )
            else:
                c.execute(
                    "INSERT INTO payment_plan (coachee_id, frequency, amount, currency, start_date) VALUES (%s,%s,%s,%s,%s)",
                    (
                        cid,
                        request.form["frequency"],
                        request.form["plan_amount"],
                        request.form.get("currency", "EUR"),
                        request.form["start_date"],
                    ),
                )
            flash("Payment plan saved.", "success")
        elif action == "deactivate_plan":
            c.execute("UPDATE payment_plan SET active=0 WHERE coachee_id=%s", (cid,))
            flash("Plan deactivated.", "success")
        return redirect(url_for("coach.coachee_payments", cid=cid))

    # Get plan
    c.execute("SELECT * FROM payment_plan WHERE coachee_id=%s", (cid,))
    plan = c.fetchone()
    # Get payment history
    c.execute("SELECT * FROM payment_log WHERE coachee_id=%s ORDER BY confirmed_at DESC LIMIT 20", (cid,))
    payments = c.fetchall()
    # Compliance
    compliance = _payment_compliance(cid)

    return render_template_string(_tpl("payments.html"), coachee=coachee, plan=plan, payments=payments, compliance=compliance)


@bp.route("/coach/coachee/<int:cid>/quick-pay", methods=["POST"])
@login_required("coach")
def quick_confirm_payment(cid):
    """Log a payment for a coachee using their active plan amount (or posted amount).

    Route POST /coach/coachee/<cid>/quick-pay — no screen; redirects to the coach dashboard.
    When: on the quick-confirm-payment button submit on the coach dashboard.
    """
    c = db()
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)
    # Get plan amount
    c.execute("SELECT amount, currency FROM payment_plan WHERE coachee_id=%s AND active=1", (cid,))
    plan = c.fetchone()
    amount = plan["amount"] if plan else request.form.get("amount", "0")
    currency = plan["currency"] if plan else "EUR"
    today = date.today().isoformat()
    c.execute(
        "INSERT INTO payment_log (coachee_id, amount, currency, period_start, notes) VALUES (%s,%s,%s,%s,%s)",
        (cid, amount, currency, today, "Quick confirm from dashboard"),
    )
    flash("Payment confirmed.", "success")
    return redirect(url_for("coach.coach_dashboard"))



@bp.route("/coach/help")
@login_required("coach")
def coach_help():
    """Render the in-app navigation guide for coaches.

    Route GET /coach/help — renders the coach help screen (coach_help.html).
    When: on help screen load from the coach navigation.
    """
    return render_template_string(_tpl("coach_help.html"))


@bp.route("/coach/photo-validation-settings", methods=["GET", "POST"])
@login_required("coach")
def photo_validation_settings():
    """Show/save coach-level AI photo-validation settings (enabled, service, API key) in coach features JSON.

    Route GET/POST /coach/photo-validation-settings — renders the photo validation settings screen
    (photo_validation_settings.html).
    When: GET on screen load; POST on the settings form submit.
    """
    c = db()
    if request.method == "POST":
        enabled = 1 if request.form.get("photo_validation_enabled") else 0
        service = request.form.get("photo_validation_service", "cloudflare")
        api_key = request.form.get("photo_validation_api_key", "")
        # Store in coach features JSON (extend existing)
        c.execute("SELECT features FROM coach WHERE id=%s", (session["user_id"],))
        row = c.fetchone()
        features = json.loads(row["features"]) if row and row["features"] and isinstance(row["features"], str) else (row["features"] if row and isinstance(row.get("features"), dict) else {})
        features["photo_validation"] = {
            "enabled": bool(enabled),
            "service": service,
            "api_key": api_key,
        }
        c.execute("UPDATE coach SET features=%s WHERE id=%s", (json.dumps(features), session["user_id"]))
        flash("Photo validation settings saved.", "success")
        return redirect(url_for("coach.photo_validation_settings"))
    c.execute("SELECT features FROM coach WHERE id=%s", (session["user_id"],))
    row = c.fetchone()
    features = json.loads(row["features"]) if row and row["features"] and isinstance(row["features"], str) else (row["features"] if row and isinstance(row.get("features"), dict) else {})
    pv = features.get("photo_validation", {"enabled": False, "service": "cloudflare", "api_key": ""})
    return render_template_string(_tpl("photo_validation_settings.html"), pv=pv)


@bp.route("/coach/coachee/<int:cid>/photo-validation", methods=["POST"])
@login_required("coach")
def update_coachee_photo_validation(cid):
    """Set the per-coachee photo-validation percentage (0–100) in the coachee features JSON.

    Route POST /coach/coachee/<cid>/photo-validation — no screen; redirects to the coachee detail screen.
    When: on the photo-validation percentage form submit within coach_view_coachee.html.
    """
    c = db()
    pct = int(request.form.get("photo_validation_pct", 0))
    pct = max(0, min(100, pct))
    c.execute("SELECT features FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    row = c.fetchone()
    if not row:
        abort(404)
    features = json.loads(row["features"]) if row["features"] and isinstance(row["features"], str) else (row["features"] if isinstance(row.get("features"), dict) else {})
    features["photo_validation_pct"] = pct
    c.execute("UPDATE coachee SET features=%s WHERE id=%s", (json.dumps(features), cid))
    flash(f"Photo validation set to {pct}%.", "success")
    return redirect(url_for("coach.coach_view_coachee", cid=cid))


@bp.route("/coach/task/<int:tid>/validate-photo", methods=["POST"])
@login_required("coach")
def coach_override_photo_validation(tid):
    """Coach overrides the AI photo-validation decision (approve, or reject → task back to pending).

    Route POST /coach/task/<tid>/validate-photo — no screen; redirects back (referrer or coach dashboard).
    When: on the approve/reject photo-override button submit from the grading or coachee detail screen.
    """
    c = db()
    decision = request.form.get("decision")  # "approve" or "reject"
    comment = request.form.get("comment", "")
    c.execute(
        """SELECT ta.coachee_id FROM task_assignment ta
           JOIN coachee ce ON ta.coachee_id=ce.id
           WHERE ta.id=%s AND ce.coach_id=%s""",
        (tid, session["user_id"]),
    )
    row = c.fetchone()
    if not row:
        abort(404)
    # Update the AI validation fields with coach override
    override_data = json.dumps({"decision": decision, "comment": comment, "by": "coach"})
    c.execute(
        "UPDATE task_assignment SET photo_validation_override=%s WHERE id=%s",
        (override_data, tid),
    )
    if decision == "reject":
        c.execute("UPDATE task_assignment SET status='pending', response=NULL, attachment_path=NULL, responded_at=NULL WHERE id=%s", (tid,))
        flash("Photo rejected — task returned to pending.", "info")
    else:
        flash("Photo validated.", "success")
    return redirect(request.referrer or url_for("coach.coach_dashboard"))


# ── Creative Writing (Coach) ──


@bp.route("/coach/coachee/<int:cid>/writing")
@login_required("coach")
def coach_view_writing(cid):
    """List a coachee's creative works, constraints, and collections.

    Route GET /coach/coachee/<cid>/writing — renders the coach writing screen (coach_writing.html).
    When: on the writing screen load from the coachee detail screen.
    """
    c = db()
    c.execute("SELECT * FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)
    c.execute("SELECT * FROM creative_work WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    works = c.fetchall()
    c.execute("SELECT * FROM creative_constraint WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    constraints = c.fetchall()
    c.execute("SELECT * FROM creative_collection WHERE coachee_id=%s ORDER BY created_at", (cid,))
    collections = c.fetchall()
    return render_template_string(
        _tpl("coach_writing.html"),
        coachee=coachee,
        works=works,
        constraints=constraints,
        collections=collections,
    )


@bp.route("/coach/coachee/<int:cid>/writing/constraint", methods=["POST"])
@login_required("coach")
def assign_constraint(cid):
    """Assign a creative constraint (subject, theme, word, constraint, emotion, style) to a coachee.

    Route POST /coach/coachee/<cid>/writing/constraint — no screen; redirects to the coach writing screen.
    When: on the assign-constraint form submit within coach_writing.html.
    """
    c = db()
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)
    constraint_type = request.form.get("constraint_type", "theme")
    constraint_value = request.form.get("constraint_value", "").strip()
    active_date = request.form.get("active_date") or None
    if not constraint_value:
        flash("Constraint value is required.", "error")
        return redirect(url_for("coach.coach_view_writing", cid=cid))
    c.execute(
        """INSERT INTO creative_constraint (coach_id, coachee_id, constraint_type, constraint_value, active_date)
           VALUES (%s,%s,%s,%s,%s)""",
        (session["user_id"], cid, constraint_type, constraint_value, active_date),
    )
    flash("Constraint assigned.", "success")
    return redirect(url_for("coach.coach_view_writing", cid=cid))


@bp.route("/coach/coachee/<int:cid>/writing/collection", methods=["POST"])
@login_required("coach")
def create_collection(cid):
    """Create a named creative collection for a coachee's works.

    Route POST /coach/coachee/<cid>/writing/collection — no screen; redirects to the coach writing screen.
    When: on the create-collection form submit within coach_writing.html.
    """
    c = db()
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not title:
        flash("Collection title is required.", "error")
        return redirect(url_for("coach.coach_view_writing", cid=cid))
    c.execute(
        "INSERT INTO creative_collection (coachee_id, title, description) VALUES (%s,%s,%s)",
        (cid, title, description),
    )
    flash("Collection created.", "success")
    return redirect(url_for("coach.coach_view_writing", cid=cid))


@bp.route("/coach/coachee/<int:cid>/writing/<int:wid>/note", methods=["POST"])
@login_required("coach")
def annotate_work(wid, cid):
    """Add coach notes/tags, select a work for the final collection, and set its collection.

    Route POST /coach/coachee/<cid>/writing/<wid>/note — no screen; redirects to the coach writing screen.
    When: on the annotate-work form submit within coach_writing.html.
    """
    c = db()
    c.execute("SELECT id FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    if not c.fetchone():
        abort(404)
    coach_notes = request.form.get("coach_notes", "").strip()
    selected = 1 if request.form.get("selected_for_final") else 0
    collection_id = request.form.get("collection_id") or None
    tags = request.form.get("tags", "").strip()
    c.execute(
        """UPDATE creative_work SET coach_notes=%s, selected_for_final=%s, collection_id=%s, tags=%s
           WHERE id=%s AND coachee_id=%s""",
        (coach_notes, selected, collection_id, tags or None, wid, cid),
    )
    flash("Work updated.", "success")
    return redirect(url_for("coach.coach_view_writing", cid=cid))


@bp.route("/coach/coachee/<int:cid>/writing/export")
@login_required("coach")
def export_collection(cid):
    """Export a coachee's full (or selected-only) creative collection as a downloadable JSON file.

    Route GET /coach/coachee/<cid>/writing/export — file download (JSON attachment); no screen.
    When: on the export button/link click on the coach writing screen (coach_writing.html); ?selected=1 limits to selected works.
    """
    c = db()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        abort(404)
    selected_only = request.args.get("selected") == "1"
    if selected_only:
        c.execute(
            "SELECT * FROM creative_work WHERE coachee_id=%s AND selected_for_final=1 ORDER BY created_at",
            (cid,),
        )
    else:
        c.execute("SELECT * FROM creative_work WHERE coachee_id=%s ORDER BY created_at", (cid,))
    works = c.fetchall()
    c.execute("SELECT * FROM creative_collection WHERE coachee_id=%s", (cid,))
    collections = c.fetchall()
    c.execute("SELECT * FROM creative_constraint WHERE coachee_id=%s", (cid,))
    constraints = c.fetchall()
    export = {
        "coachee": coachee["name"],
        "total_works": len(works),
        "collections": [dict(col) for col in collections],
        "constraints": [dict(con) for con in constraints],
        "works": [dict(w) for w in works],
    }
    return Response(
        json.dumps(export, default=str, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=creative_collection_{cid}.json"},
    )
