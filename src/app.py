import os
import hashlib
import secrets
import json
import random
import base64
from functools import wraps
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, request, redirect, url_for, session, render_template_string, g
from db import get_db, init_db

app = Flask(__name__, template_folder="/src/templates", static_folder="/static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
ATTACHMENTS_DIR = os.environ.get("ATTACHMENTS_DIR", "/data/attachments")


def _audit(action, user_id=None, role=None):
    try:
        c = db().cursor()
        c.execute("INSERT INTO audit_log (user_id, role, action, ip, user_agent) VALUES (%s,%s,%s,%s,%s)",
                  (user_id or session.get("user_id", 0), role or session.get("role", ""),
                   action, request.remote_addr, str(request.user_agent)[:500]))
    except Exception:
        pass


def _hash(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def _tpl(name):
    with open(os.path.join(TEMPLATES_DIR, name)) as f:
        return f.read()


def login_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session or session.get("role") != role:
                return redirect(url_for("login"))
            return fn(*a, **kw)
        return wrapper
    return decorator


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session or session.get("role") != "coach" or not session.get("is_admin"):
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


def db():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def _auto_assign_reserves(coachee_id, coach_id):
    """If no task was manually assigned today for this coachee, pick one reserve task."""
    c = db().cursor()
    c.execute("SELECT timezone, task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (coachee_id,))
    cc = c.fetchone()
    tz = ZoneInfo((cc["timezone"]) or "UTC")
    local_today = datetime.now(tz).date().isoformat()

    def _assign(tmpl_id, due):
        vis = f"{due} {cc['task_unveil_time']}" if cc["task_unveil_time"] else None
        frz = f"{due} {cc['task_freeze_time']}" if cc["task_freeze_time"] else None
        c.execute("INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                  (tmpl_id, coachee_id, due, vis, frz))

    # recurring tasks: auto-assign if due
    c.execute("""SELECT tt.id, tt.recur_days, tt.recur_approx FROM task_template tt
                 WHERE tt.coach_id=%s AND tt.recur_days IS NOT NULL AND tt.recur_days > 0 AND tt.is_reserve=0""", (coach_id,))
    for tmpl in c.fetchall():
        c.execute("SELECT MAX(due_date) as last_due FROM task_assignment WHERE template_id=%s AND coachee_id=%s", (tmpl["id"], coachee_id))
        last = c.fetchone()["last_due"]
        if last:
            days = tmpl["recur_days"]
            if tmpl["recur_approx"]:
                days = max(1, days + random.randint(-max(1, days // 4), max(1, days // 4)))
            next_due = (last + timedelta(days=days)).isoformat()
            if next_due <= local_today:
                _assign(tmpl["id"], local_today)
        # if never assigned to this coachee, assign now
        elif True:
            _assign(tmpl["id"], local_today)

    # reserve tasks: only if no task today at all
    c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND due_date=%s", (coachee_id, local_today))
    if c.fetchone()["cnt"] > 0:
        return
    c.execute("""SELECT tt.id FROM task_template tt
                 WHERE tt.coach_id=%s AND tt.is_reserve=1
                 AND tt.id NOT IN (SELECT template_id FROM task_assignment WHERE coachee_id=%s)
                 ORDER BY RAND() LIMIT 1""", (coach_id, coachee_id))
    row = c.fetchone()
    if row:
        _assign(row["id"], local_today)


def _freeze_overdue(coachee_id, tz):
    """Mark pending tasks as missed if past freeze time, add strikes, reset streak."""
    c = db().cursor()
    local_now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment
                 WHERE coachee_id=%s AND status='pending' AND frozen_after IS NOT NULL AND frozen_after < %s""",
              (coachee_id, local_now))
    missed = c.fetchone()["cnt"]
    if missed:
        c.execute("""UPDATE task_assignment SET status='missed'
                     WHERE coachee_id=%s AND status='pending' AND frozen_after IS NOT NULL AND frozen_after < %s""",
                  (coachee_id, local_now))
        c.execute("UPDATE coachee SET strikes=strikes+%s, current_streak=0 WHERE id=%s", (missed, coachee_id))


def _update_streak(coachee_id, tz):
    """Update streak if all tasks for yesterday were completed on time."""
    c = db().cursor()
    local_today = datetime.now(tz).date()
    yesterday = (local_today - timedelta(days=1)).isoformat()
    c.execute("SELECT last_streak_date FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if row["last_streak_date"] and str(row["last_streak_date"]) >= yesterday:
        return  # already checked
    c.execute("SELECT COUNT(*) as total FROM task_assignment WHERE coachee_id=%s AND due_date=%s", (coachee_id, yesterday))
    total = c.fetchone()["total"]
    if total == 0:
        return  # no tasks yesterday
    c.execute("SELECT COUNT(*) as done FROM task_assignment WHERE coachee_id=%s AND due_date=%s AND status='completed'", (coachee_id, yesterday))
    if c.fetchone()["done"] == total:
        c.execute("""UPDATE coachee SET current_streak=current_streak+1,
                     best_streak=GREATEST(best_streak, current_streak+1),
                     last_streak_date=%s WHERE id=%s""", (yesterday, coachee_id))
    else:
        c.execute("UPDATE coachee SET current_streak=0, last_streak_date=%s WHERE id=%s", (yesterday, coachee_id))


def _visible_tasks(coachee_id, tz):
    """Get tasks that are visible, not frozen, and whose dependencies are met."""
    c = db().cursor()
    local_now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""SELECT ta.*, tt.title, tt.description as task_desc, tt.category, tt.difficulty
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.status IN ('pending','partial')
                 AND (ta.visible_after IS NULL OR ta.visible_after <= %s)
                 AND (ta.frozen_after IS NULL OR ta.frozen_after > %s)
                 AND (ta.depends_on IS NULL OR ta.depends_on IN
                      (SELECT id FROM task_assignment WHERE status='completed'))
                 ORDER BY ta.due_date""", (coachee_id, local_now, local_now))
    return c.fetchall()


MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
LLM_KEY = MISTRAL_KEY

def _build_profile_prompt(coachee_id):
    """Build the Gemini prompt from coachee history. Returns (prompt, name) or (None, None)."""
    c = db().cursor()
    c.execute("SELECT name, context_text FROM coachee WHERE id=%s", (coachee_id,))
    coachee_row = c.fetchone()
    if not coachee_row:
        return None
    name = coachee_row["name"]
    c.execute("SELECT checkin_type, content, created_at FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (coachee_id,))
    checkins = c.fetchall()
    c.execute("""SELECT tt.title, ta.status, ta.response, ta.created_at FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id WHERE ta.coachee_id=%s ORDER BY ta.created_at DESC LIMIT 30""", (coachee_id,))
    tasks = c.fetchall()
    c.execute("SELECT category, content, created_at FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 30", (coachee_id,))
    tracking = c.fetchall()
    c.execute("SELECT author_role, content, created_at FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (coachee_id,))
    notes = c.fetchall()
    c.execute("SELECT ack_type, description FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (coachee_id,))
    acks = c.fetchall()

    def fmt(rows):
        return "\n".join(f"  [{r.get('created_at','')}] {dict(r)}" for r in rows) or "  (none)"

    prompt = f"""You are a coaching psychology assistant. Based on the following data for coachee "{name}", write a concise psychological profile (max 300 words) to help their coach understand them better. Cover: emotional patterns, discipline/consistency, areas of strength, areas needing attention, and overall trajectory. Be empathetic but honest. Use third person ("{name}" or "they").

CHECK-INS:
{fmt(checkins)}

TASKS (status & responses):
{fmt(tasks)}

TRACKING (food/hydration/exercise/emotional):
{fmt(tracking)}

NOTES (coach-coachee communication):
{fmt(notes)}

ACKNOWLEDGEMENTS:
{fmt(acks)}"""

    ctx = coachee_row.get("context_text") or ""
    if ctx:
        prompt += f"\n\nPAST EXCHANGES / ADDITIONAL CONTEXT:\n{ctx[:10000]}"
    return prompt

# ── Auth ──

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("coach_dashboard" if session["role"] == "coach" else "coachee_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        username = request.form["username"]
        pw = _hash(request.form["password"])
        c = db().cursor()
        c.execute("SELECT id, name, timezone, accent_color, bg_color, card_color, is_admin, status FROM coach WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            if row.get("status") == "frozen":
                err = "Account frozen. Contact administrator."
            else:
                session.update(user_id=row["id"], role="coach", name=row["name"],
                               timezone=row["timezone"] or "Europe/London",
                               accent=row["accent_color"] or "#e94560",
                               bg=row["bg_color"] or "#1a1a2e",
                               card=row["card_color"] or "#16213e",
                               is_admin=bool(row.get("is_admin")))
                _audit("login", row["id"], "coach")
                return redirect(url_for("coach_dashboard"))
        c.execute("SELECT id, name, coach_id, color_scheme, avatar FROM coachee WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            c.execute("SELECT accent_color, bg_color, card_color, status FROM coach WHERE id=%s", (row["coach_id"],))
            coach_brand = c.fetchone()
            if coach_brand.get("status") == "frozen":
                err = "Your coach's account is frozen."
            else:
                session.update(user_id=row["id"], role="coachee", name=row["name"], coach_id=row["coach_id"],
                               accent=row["color_scheme"] or coach_brand["accent_color"] or "#e94560",
                               bg=coach_brand["bg_color"] or "#1a1a2e",
                               card=coach_brand["card_color"] or "#16213e",
                               avatar=row["avatar"] or "🐕")
                _audit("login", row["id"], "coachee")
                return redirect(url_for("coachee_dashboard"))
        err = "Invalid credentials"
    return render_template_string(_tpl("login.html"), error=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    c = db().cursor()
    c.execute("SELECT COUNT(*) as cnt FROM coach")
    if c.fetchone()["cnt"] > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        c.execute("INSERT INTO coach (username, password_hash, name, timezone, is_admin) VALUES (%s,%s,%s,%s,1)",
                  (request.form["username"], _hash(request.form["password"]), request.form["name"],
                   request.form.get("timezone", "Europe/London")))
        return redirect(url_for("login"))
    return render_template_string(_tpl("setup.html"))


# ── Coach views ──

@app.route("/coach")
@login_required("coach")
def coach_dashboard():
    c = db().cursor()
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
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='completed' AND grade IS NULL", (cc["id"],))
        cc["ungraded"] = c.fetchone()["cnt"]
        c.execute("SELECT AVG(FIELD(grade,'A','B','C','D','E','F')) as avg_g FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL", (cc["id"],))
        avg = c.fetchone()["avg_g"]
        cc["avg_grade"] = chr(64 + round(avg)) if avg else "—"
        cc["strikes"] = cc.get("strikes") or 0
        cc["current_streak"] = cc.get("current_streak") or 0
        c.execute("SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s AND DATE(created_at)=%s", (cc["id"],
                  datetime.now(ZoneInfo(cc["timezone"] or "UTC")).date().isoformat()))
        cc["checkins_today"] = c.fetchone()["cnt"]
    # total ungraded for nav badge
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id
                 WHERE ce.coach_id=%s AND ta.status='completed' AND ta.grade IS NULL""", (session["user_id"],))
    ungraded_total = c.fetchone()["cnt"]
    return render_template_string(_tpl("coach_dashboard.html"), coachees=coachees, ungraded_total=ungraded_total)


FEATURES = [
    ("tasks", "📋 Tasks & Grading"),
    ("checkins", "📖 Check-ins"),
    ("tracking", "📊 Tracking"),
    ("conditioning", "🧠 Mental Conditioning"),
    ("notes", "💬 Notes & Voice"),
    ("goals", "🎯 Goal Setting"),
    ("journal", "📓 Journaling"),
    ("photos", "📸 Progress Photos"),
    ("ai_profile", "🪞 AI Profile"),
    ("telegram", "📱 Telegram Notifications"),
]


def _features_for(coach_id, coachee_id=None):
    """Get effective feature flags. Coach global, optionally overridden per coachee."""
    c = db().cursor()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    coach_f = json.loads(row["features"]) if row and row["features"] else {k: True for k, _ in FEATURES}
    if not coachee_id:
        return coach_f
    c.execute("SELECT features FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    coachee_f = json.loads(row["features"]) if row and row["features"] else {}
    # coachee can only disable what coach enabled
    return {k: coach_f.get(k, True) and coachee_f.get(k, True) for k, _ in FEATURES}


@app.route("/coach/settings", methods=["GET", "POST"])
@login_required("coach")
def coach_settings():
    c = db().cursor()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            old_pw = _hash(request.form["old_password"])
            c.execute("SELECT id FROM coach WHERE id=%s AND password_hash=%s", (session["user_id"], old_pw))
            if c.fetchone():
                c.execute("UPDATE coach SET password_hash=%s WHERE id=%s", (_hash(request.form["new_password"]), session["user_id"]))
                _audit("change_password")
        elif action == "name":
            new_name = request.form["name"].strip()
            if new_name:
                c.execute("UPDATE coach SET name=%s WHERE id=%s", (new_name, session["user_id"]))
                session["name"] = new_name
        elif action == "features":
            features = {k: k in request.form.getlist("features") for k, _ in FEATURES}
            c.execute("UPDATE coach SET features=%s WHERE id=%s", (json.dumps(features), session["user_id"]))
        return redirect(url_for("coach_settings"))
    c.execute("SELECT name, features FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    coach_features = json.loads(coach["features"]) if coach["features"] else {k: True for k, _ in FEATURES}
    return render_template_string(_tpl("coach_settings.html"), coach=coach, features=FEATURES, coach_features=coach_features)


@app.route("/coach/change-password", methods=["POST"])
@login_required("coach")
def coach_change_password():
    c = db().cursor()
    old_pw = _hash(request.form["old_password"])
    c.execute("SELECT id FROM coach WHERE id=%s AND password_hash=%s", (session["user_id"], old_pw))
    if not c.fetchone():
        return redirect(url_for("coach_settings"))
    c.execute("UPDATE coach SET password_hash=%s WHERE id=%s", (_hash(request.form["new_password"]), session["user_id"]))
    _audit("change_password")
    return redirect(url_for("coach_settings"))


@app.route("/coach/change-name", methods=["POST"])
@login_required("coach")
def coach_change_name():
    c = db().cursor()
    new_name = request.form["name"].strip()
    if new_name:
        c.execute("UPDATE coach SET name=%s WHERE id=%s", (new_name, session["user_id"]))
        session["name"] = new_name
    return redirect(url_for("coach_branding"))


@app.route("/coach/support", methods=["GET", "POST"])
@login_required("coach")
def coach_support():
    c = db().cursor()
    if request.method == "POST":
        # grab last 10 audit actions for this coach
        c.execute("SELECT action, created_at FROM audit_log WHERE user_id=%s AND role='coach' ORDER BY created_at DESC LIMIT 10", (session["user_id"],))
        actions = c.fetchall()
        actions_text = "\n".join(f"[{a['created_at']}] {a['action']}" for a in actions)
        c.execute("INSERT INTO support_message (coach_id, message, recent_actions) VALUES (%s,%s,%s)",
                  (session["user_id"], request.form["message"], actions_text))
        _audit("support_message")
        return redirect(url_for("coach_support"))
    c.execute("SELECT * FROM support_message WHERE coach_id=%s ORDER BY created_at DESC LIMIT 20", (session["user_id"],))
    messages = c.fetchall()
    return render_template_string(_tpl("coach_support.html"), messages=messages)


@app.route("/features")
def features_page():
    return render_template_string(_tpl("features.html"))


@app.route("/coach/branding", methods=["GET", "POST"])
@login_required("coach")
def coach_branding():
    c = db().cursor()
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
            c.execute("UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s, logo_path=%s WHERE id=%s",
                      (accent, bg, card, tg_token, logo_path, session["user_id"]))
        else:
            c.execute("UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s WHERE id=%s",
                      (accent, bg, card, tg_token, session["user_id"]))
        session.update(accent=accent, bg=bg, card=card)
        return redirect(url_for("coach_branding"))
    c.execute("SELECT accent_color, bg_color, card_color, telegram_bot_token, logo_path IS NOT NULL as has_logo FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    return render_template_string(_tpl("coach_branding.html"), coach=coach)


@app.route("/coach/logo")
def coach_logo():
    cid = request.args.get("id") or (session.get("coach_id") if session.get("role") == "coachee" else session.get("user_id"))
    if not cid:
        return "", 404
    c = db().cursor()
    c.execute("SELECT logo_path FROM coach WHERE id=%s", (cid,))
    row = c.fetchone()
    if not row or not row["logo_path"]:
        return "", 404
    try:
        with open(row["logo_path"], "rb") as f:
            data = f.read()
        from flask import Response
        return Response(data, mimetype="image/png")
    except FileNotFoundError:
        return "", 404


@app.route("/coach/coachee/add", methods=["GET", "POST"])
@login_required("coach")
def add_coachee():
    if request.method == "POST":
        c = db().cursor()
        c.execute("""INSERT INTO coachee (username, password_hash, name, coach_id, contract_text, safe_word,
                     task_unveil_time, task_freeze_time, timezone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (request.form["username"], _hash(request.form["password"]), request.form["name"],
                   session["user_id"], request.form.get("contract", ""), request.form.get("safe_word", "RED"),
                   request.form.get("task_unveil_time", "08:00"), request.form.get("task_freeze_time", "22:00"),
                   request.form.get("timezone", "Europe/London")))
        return redirect(url_for("coach_dashboard"))
    c = db().cursor()
    c.execute("SELECT timezone FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    return render_template_string(_tpl("add_coachee.html"), coach_tz=coach["timezone"] or "Europe/London")


@app.route("/coach/coachee/<int:cid>")
@login_required("coach")
def coach_view_coachee(cid):
    c = db().cursor()
    c.execute("SELECT * FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        return "Not found", 404
    # format timedelta TIME columns for HTML time inputs
    for k in ("task_unveil_time", "task_freeze_time"):
        v = coachee[k]
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            coachee[k] = f"{total//3600:02d}:{(total%3600)//60:02d}"
    c.execute("""SELECT ta.*, tt.title, tt.category FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s ORDER BY ta.created_at DESC LIMIT 20""", (cid,))
    tasks = c.fetchall()
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    checkins = c.fetchall()
    c.execute("SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    acks = c.fetchall()
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
    logs = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY pinned DESC, created_at DESC LIMIT 20", (cid,))
    notes = c.fetchall()
    c.execute("""SELECT mc.*, mcr.content as response, mcr.created_at as response_at
                 FROM mental_conditioning mc
                 LEFT JOIN mental_conditioning_response mcr ON mcr.conditioning_id=mc.id AND mcr.coachee_id=%s
                 WHERE mc.target='all' OR mc.coachee_id=%s
                 ORDER BY mc.prompt_date DESC LIMIT 20""", (cid, cid))
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
    c.execute("SELECT * FROM journal WHERE coachee_id=%s AND visible_to_coach=1 ORDER BY created_at DESC LIMIT 10", (cid,))
    journals = c.fetchall()
    c.execute("SELECT * FROM progress_photo WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    photos = c.fetchall()
    return render_template_string(_tpl("coach_view_coachee.html"),
                                 coachee=coachee, tasks=tasks, checkins=checkins,
                                 acks=acks, logs=logs, notes=notes, conditioning=conditioning,
                                 profile_text=profile_text, voice_notes=voice_notes,
                                 goals=goals, journals=journals, photos=photos,
                                 coachee_context=coachee.get("context_text", ""),
                                 llm_key=LLM_KEY, tg_token=tg_token or "",
                                 coach_tz=session.get("timezone", "Europe/London"),
                                 all_features=FEATURES,
                                 coachee_features=json.loads(coachee.get("features") or "null") or {k: True for k, _ in FEATURES})


@app.route("/coach/coachee/<int:cid>/edit", methods=["POST"])
@login_required("coach")
def edit_coachee(cid):
    c = db().cursor()
    new_contract = request.form.get("contract", "")
    # version contract if changed
    c.execute("SELECT contract_text FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    old = c.fetchone()
    if old and old["contract_text"] and old["contract_text"] != new_contract:
        c.execute("INSERT INTO contract_history (coachee_id, contract_text) VALUES (%s,%s)", (cid, old["contract_text"]))
    coachee_features = {k: k in request.form.getlist("coachee_features") for k, _ in FEATURES}
    c.execute("""UPDATE coachee SET contract_text=%s, safe_word=%s, task_unveil_time=%s, task_freeze_time=%s,
                 timezone=%s, avatar=%s, color_scheme=%s, telegram_chat_id=%s, features=%s
                 WHERE id=%s AND coach_id=%s""",
              (new_contract, request.form.get("safe_word", "RED"),
               request.form.get("task_unveil_time", "08:00"), request.form.get("task_freeze_time", "22:00"),
               request.form.get("timezone", "Europe/London"),
               request.form.get("avatar", "🐕"), request.form.get("color_scheme", "#e94560"),
               request.form.get("telegram_chat_id", ""),
               json.dumps(coachee_features),
               cid, session["user_id"]))
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/coach/coachee/<int:cid>/context", methods=["POST"])
@login_required("coach")
def save_coachee_context(cid):
    c = db().cursor()
    c.execute("UPDATE coachee SET context_text=%s WHERE id=%s AND coach_id=%s",
              (request.form.get("context_text", ""), cid, session["user_id"]))
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/coach/coachee/<int:cid>/profile-prompt")
@login_required("coach")
def get_profile_prompt(cid):
    prompt = _build_profile_prompt(cid)
    return json.dumps({"prompt": prompt}), 200, {"Content-Type": "application/json"}


@app.route("/coach/coachee/<int:cid>/profile", methods=["POST"])
@login_required("coach")
def save_profile(cid):
    text = request.json.get("text", "") if request.is_json else ""
    if text:
        c = db().cursor()
        c.execute("""INSERT INTO psychological_profile (coachee_id, profile_text) VALUES (%s,%s)
                     ON DUPLICATE KEY UPDATE profile_text=%s""", (cid, text, text))
    return "", 204


@app.route("/coach/analyze")
@login_required("coach")
def analyze_text():
    return render_template_string(_tpl("analyze.html"), llm_key=LLM_KEY)


@app.route("/coach/grading", methods=["GET", "POST"])
@login_required("coach")
def bulk_grading():
    c = db().cursor()
    if request.method == "POST":
        for key, val in request.form.items():
            if key.startswith("grade_") and val:
                tid = int(key.split("_")[1])
                comment = request.form.get(f"comment_{tid}", "")
                c.execute("""UPDATE task_assignment SET grade=%s, coach_comment=%s
                             WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
                          (val, comment, tid, session["user_id"]))
        return redirect(url_for("bulk_grading"))
    c.execute("""SELECT ta.id, ta.response, ta.responded_at, ta.grade, ta.coach_comment,
                        ta.attachment_path IS NOT NULL as has_attachment,
                        tt.title, tt.category, ce.name as coachee_name
                 FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 JOIN coachee ce ON ta.coachee_id=ce.id
                 WHERE ce.coach_id=%s AND ta.status='completed' AND ta.grade IS NULL
                 ORDER BY ta.responded_at DESC""", (session["user_id"],))
    tasks = c.fetchall()
    return render_template_string(_tpl("bulk_grading.html"), tasks=tasks)


@app.route("/coach/tasks", methods=["GET", "POST"])
@login_required("coach")
def manage_tasks():
    c = db().cursor()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "assign_library":
            # assign existing library template
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
                c.execute("INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                          (tmpl_id, cid, d, vis, frz))
            return redirect(url_for("manage_tasks"))
        # create new
        is_reserve = 1 if request.form.get("is_reserve") else 0
        in_library = 1 if request.form.get("in_library") else 0
        recur_days = int(request.form.get("recur_days") or 0) or None
        recur_approx = 1 if request.form.get("recur_approx") else 0
        c.execute("""INSERT INTO task_template (coach_id, title, description, recurrence, category, difficulty, is_reserve, recur_days, recur_approx, in_library)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (session["user_id"], request.form["title"], request.form["description"],
                   request.form["recurrence"], request.form["category"], request.form.get("difficulty", "medium"),
                   is_reserve, recur_days, recur_approx, in_library))
        tmpl_id = c.lastrowid
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
                c.execute("INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                          (tmpl_id, cid, due or today, vis, frz))
        return redirect(url_for("manage_tasks"))
    c.execute("SELECT * FROM task_template WHERE coach_id=%s ORDER BY created_at DESC", (session["user_id"],))
    templates = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s ORDER BY name", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("manage_tasks.html"), templates=templates, coachees=coachees)


@app.route("/coach/library-search")
@login_required("coach")
def library_search():
    c = db().cursor()
    c.execute("SELECT id, title, description, category FROM task_template WHERE coach_id=%s AND in_library=1 ORDER BY title", (session["user_id"],))
    templates = c.fetchall()
    # get usage stats per coachee for each template
    for t in templates:
        c.execute("""SELECT ce.id, ce.name, COUNT(ta.id) as times, MAX(ta.due_date) as last_date
                     FROM coachee ce LEFT JOIN task_assignment ta ON ta.coachee_id=ce.id AND ta.template_id=%s
                     WHERE ce.coach_id=%s GROUP BY ce.id, ce.name ORDER BY ce.name""", (t["id"], session["user_id"]))
        t["usage"] = {str(r["id"]): {"times": r["times"], "last": str(r["last_date"]) if r["last_date"] else None} for r in c.fetchall()}
    return json.dumps([dict(t) for t in templates], default=str), 200, {"Content-Type": "application/json"}


@app.route("/coach/conditioning", methods=["GET", "POST"])
@login_required("coach")
def manage_conditioning():
    c = db().cursor()
    if request.method == "POST":
        target = request.form["target"]
        coachee_id = request.form.get("coachee_id") if target == "individual" else None
        c.execute("INSERT INTO mental_conditioning (coach_id, prompt_date, prompt_text, target, coachee_id) VALUES (%s,%s,%s,%s,%s)",
                  (session["user_id"], request.form.get("prompt_date", date.today().isoformat()),
                   request.form["prompt_text"], target, coachee_id))
        return redirect(url_for("manage_conditioning"))
    c.execute("""SELECT mc.*, co.name as coachee_name FROM mental_conditioning mc
                 LEFT JOIN coachee co ON mc.coachee_id=co.id
                 WHERE mc.coach_id=%s ORDER BY prompt_date DESC LIMIT 30""", (session["user_id"],))
    prompts = c.fetchall()
    c.execute("SELECT id, name FROM coachee WHERE coach_id=%s", (session["user_id"],))
    coachees = c.fetchall()
    return render_template_string(_tpl("manage_conditioning.html"), prompts=prompts, coachees=coachees)


@app.route("/coach/ack/<int:cid>", methods=["POST"])
@login_required("coach")
def give_acknowledgement(cid):
    c = db().cursor()
    c.execute("INSERT INTO acknowledgement (coachee_id, coach_id, ack_type, description, notes) VALUES (%s,%s,%s,%s,%s)",
              (cid, session["user_id"], request.form["ack_type"], request.form["description"], request.form.get("notes", "")))
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/coach/task/<int:tid>/review", methods=["POST"])
@login_required("coach")
def review_task(tid):
    c = db().cursor()
    c.execute("""UPDATE task_assignment SET grade=%s, coach_comment=%s
                 WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
              (request.form.get("grade"), request.form.get("coach_comment", ""),
               tid, session["user_id"]))
    cid = request.form.get("coachee_id")
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/task/<int:tid>/attachment")
def task_attachment(tid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    c = db().cursor()
    c.execute("SELECT attachment_path, coachee_id FROM task_assignment WHERE id=%s", (tid,))
    row = c.fetchone()
    if not row or not row["attachment_path"]:
        return "Not found", 404
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        return "Forbidden", 403
    try:
        with open(row["attachment_path"], "rb") as f:
            data = f.read()
        from flask import Response
        return Response(data, mimetype="image/jpeg")
    except FileNotFoundError:
        return "Not found", 404


@app.route("/coach/note/<int:cid>", methods=["POST"])
@login_required("coach")
def coach_add_note(cid):
    c = db().cursor()
    scheduled = request.form.get("scheduled_at") or None
    c.execute("INSERT INTO note (coachee_id, author_role, content, scheduled_at) VALUES (%s,'coach',%s,%s)",
              (cid, request.form["content"], scheduled))
    return redirect(url_for("coach_view_coachee", cid=cid))


# ── Coachee views ──

@app.route("/me")
@login_required("coachee")
def coachee_dashboard():
    c = db().cursor()
    cid = session["user_id"]
    c.execute("SELECT * FROM coachee WHERE id=%s", (cid,))
    coachee = c.fetchone()

    # auto-assign reserve if past unveil time and no task today
    tz = ZoneInfo(coachee["timezone"] or "UTC")
    local_now = datetime.now(tz)
    now = local_now - datetime.combine(local_now.date(), datetime.min.time(), tz)
    if coachee["task_unveil_time"] and now >= coachee["task_unveil_time"]:
        _auto_assign_reserves(cid, coachee["coach_id"])

    _freeze_overdue(cid, tz)
    _update_streak(cid, tz)

    tasks = _visible_tasks(cid, tz)
    local_today = datetime.now(tz).date().isoformat()

    c.execute("""SELECT mc.* FROM mental_conditioning mc
                 WHERE (mc.target='all' OR mc.coachee_id=%s) AND mc.prompt_date=%s
                 AND mc.id NOT IN (SELECT conditioning_id FROM mental_conditioning_response WHERE coachee_id=%s)""", (cid, local_today, cid))
    conditioning = c.fetchall()
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s AND DATE(created_at)=%s ORDER BY created_at", (cid, local_today))
    today_checkins = c.fetchall()
    c.execute("SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    acks = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s AND (scheduled_at IS NULL OR scheduled_at <= NOW()) ORDER BY created_at DESC LIMIT 10", (cid,))
    notes = c.fetchall()
    # mark unread coach notes as read
    c.execute("UPDATE note SET read_at=NOW() WHERE coachee_id=%s AND author_role='coach' AND read_at IS NULL AND (scheduled_at IS NULL OR scheduled_at <= NOW())", (cid,))
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s AND DATE(created_at)=%s ORDER BY created_at", (cid, local_today))
    today_tracking = c.fetchall()

    # badge counts
    has_morning = any(ci["checkin_type"] == "morning" for ci in today_checkins)
    has_evening = any(ci["checkin_type"] == "evening" for ci in today_checkins)
    unread_notes = 0  # could track read status later
    pending_conditioning = len(conditioning)

    badges = {
        "tasks": len(tasks),
        "morning": 0 if has_morning else 1,
        "evening": 0 if has_evening else 1,
        "conditioning": pending_conditioning,
        "notes": unread_notes,
    }

    c.execute("""SELECT ta.*, tt.title FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.grade IS NOT NULL ORDER BY ta.responded_at DESC LIMIT 10""", (cid,))
    graded_tasks = c.fetchall()

    c.execute("SELECT * FROM goal WHERE coachee_id=%s ORDER BY FIELD(status,'active','approved','proposed','completed','rejected'), created_at DESC", (cid,))
    goals = c.fetchall()
    c.execute("SELECT * FROM journal WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    journals = c.fetchall()
    c.execute("SELECT * FROM voice_note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    voice_notes = c.fetchall()
    c.execute("SELECT * FROM progress_photo WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    photos = c.fetchall()

    return render_template_string(_tpl("coachee_dashboard.html"),
                                 coachee=coachee, tasks=tasks, conditioning=conditioning,
                                 today_checkins=today_checkins, acks=acks, notes=notes,
                                 today_tracking=today_tracking, badges=badges,
                                 graded_tasks=graded_tasks, goals=goals, journals=journals,
                                 voice_notes=voice_notes, photos=photos,
                                 feat=_features_for(coachee["coach_id"], cid))


@app.route("/me/checkin", methods=["POST"])
@login_required("coachee")
def submit_checkin():
    c = db().cursor()
    c.execute("INSERT INTO checkin (coachee_id, checkin_type, content) VALUES (%s,%s,%s)",
              (session["user_id"], request.form["checkin_type"], request.form["content"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/task/<int:tid>", methods=["POST"])
@login_required("coachee")
def complete_task(tid):
    c = db().cursor()
    c.execute("SELECT frozen_after FROM task_assignment WHERE id=%s AND coachee_id=%s", (tid, session["user_id"]))
    row = c.fetchone()
    if row and row["frozen_after"] and datetime.now() > row["frozen_after"]:
        return redirect(url_for("coachee_dashboard"))
    att_path = None
    att_data = request.form.get("attachment_data")
    if att_data and att_data.startswith("data:image"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        att_path = f"{ATTACHMENTS_DIR}/{session['user_id']}_{tid}_{int(datetime.now().timestamp())}.jpg"
        with open(att_path, "wb") as f:
            f.write(base64.b64decode(att_data.split(",", 1)[1]))
    status = request.form.get("status", "completed")
    if status not in ("completed", "partial"):
        status = "completed"
    c.execute("""UPDATE task_assignment SET status=%s, response=%s, attachment_path=%s, responded_at=NOW(),
                 reflection_rating=%s, reflection_text=%s
                 WHERE id=%s AND coachee_id=%s""",
              (status, request.form["response"], att_path,
               request.form.get("reflection_rating") or None, request.form.get("reflection_text") or None,
               tid, session["user_id"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/conditioning/<int:mid>", methods=["POST"])
@login_required("coachee")
def respond_conditioning(mid):
    c = db().cursor()
    c.execute("INSERT INTO mental_conditioning_response (conditioning_id, coachee_id, content) VALUES (%s,%s,%s)",
              (mid, session["user_id"], request.form["content"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/tracking", methods=["POST"])
@login_required("coachee")
def submit_tracking():
    c = db().cursor()
    c.execute("INSERT INTO tracking_log (coachee_id, category, content) VALUES (%s,%s,%s)",
              (session["user_id"], request.form["category"], request.form["content"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/note", methods=["POST"])
@login_required("coachee")
def coachee_add_note():
    c = db().cursor()
    c.execute("INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coachee',%s)",
              (session["user_id"], request.form["content"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/pause", methods=["POST"])
@login_required("coachee")
def trigger_pause():
    c = db().cursor()
    word = request.form.get("word", "pause")
    new_status = "stopped" if word.upper() == "RED" else "paused"
    c.execute("UPDATE coachee SET status=%s WHERE id=%s", (new_status, session["user_id"]))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/history")
@login_required("coachee")
def coachee_history():
    c = db().cursor()
    cid = session["user_id"]
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    checkins = c.fetchall()
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    logs = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50", (cid,))
    notes = c.fetchall()
    return render_template_string(_tpl("coachee_history.html"), checkins=checkins, logs=logs, notes=notes)


@app.route("/coach/note/<int:nid>/pin", methods=["POST"])
@login_required("coach")
def pin_note(nid):
    c = db().cursor()
    c.execute("UPDATE note SET pinned=NOT pinned WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)", (nid, session["user_id"]))
    return redirect(request.referrer or url_for("coach_dashboard"))


@app.route("/coach/quick-note/<int:cid>", methods=["POST"])
@login_required("coach")
def quick_note(cid):
    c = db().cursor()
    c.execute("INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)", (cid, request.form["content"]))
    return redirect(url_for("coach_dashboard"))


@app.route("/coach/quick-ack/<int:cid>", methods=["POST"])
@login_required("coach")
def quick_ack(cid):
    c = db().cursor()
    c.execute("INSERT INTO acknowledgement (coachee_id, coach_id, ack_type, description) VALUES (%s,%s,%s,%s)",
              (cid, session["user_id"], request.form["ack_type"], request.form["description"]))
    return redirect(url_for("coach_dashboard"))


@app.route("/coach/audit")
@login_required("coach")
def audit_log():
    c = db().cursor()
    c.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100")
    logs = c.fetchall()
    return render_template_string(_tpl("audit_log.html"), logs=logs)


@app.route("/coach/coachee/<int:cid>/contracts")
@login_required("coach")
def contract_history(cid):
    c = db().cursor()
    c.execute("SELECT * FROM contract_history WHERE coachee_id=%s ORDER BY created_at DESC", (cid,))
    history = c.fetchall()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    return render_template_string(_tpl("contract_history.html"), history=history, coachee=coachee)


@app.route("/coach/coachee/<int:cid>/summary")
@login_required("coach")
def weekly_summary(cid):
    c = db().cursor()
    c.execute("SELECT name, timezone FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        return "Not found", 404
    tz = ZoneInfo(coachee["timezone"] or "UTC")
    today = datetime.now(tz).date()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end = today.isoformat()
    c.execute("SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s", (cid, week_start, week_end))
    total = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND status='completed'", (cid, week_start, week_end))
    completed = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) as n FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND status='missed'", (cid, week_start, week_end))
    missed = c.fetchone()["n"]
    c.execute("SELECT AVG(FIELD(grade,'A','B','C','D','E','F')) as avg_g FROM task_assignment WHERE coachee_id=%s AND due_date BETWEEN %s AND %s AND grade IS NOT NULL", (cid, week_start, week_end))
    avg = c.fetchone()["avg_g"]
    avg_grade = chr(64 + round(avg)) if avg else "—"
    c.execute("SELECT COUNT(*) as n FROM checkin WHERE coachee_id=%s AND DATE(created_at) BETWEEN %s AND %s", (cid, week_start, week_end))
    checkins = c.fetchone()["n"]
    c.execute("SELECT current_streak, best_streak, strikes FROM coachee WHERE id=%s", (cid,))
    streaks = c.fetchone()
    summary = {"week_start": week_start, "week_end": week_end, "total": total, "completed": completed,
               "missed": missed, "avg_grade": avg_grade, "checkins": checkins, **streaks}
    return render_template_string(_tpl("weekly_summary.html"), coachee=coachee, s=summary)


@app.route("/me/export")
@login_required("coachee")
def data_export():
    c = db().cursor()
    cid = session["user_id"]
    data = {}
    c.execute("SELECT name, username, created_at, contract_text, safe_word, status FROM coachee WHERE id=%s", (cid,))
    data["profile"] = dict(c.fetchone())
    for table, q in [("checkins", "SELECT * FROM checkin WHERE coachee_id=%s ORDER BY created_at"),
                     ("tasks", """SELECT ta.*, tt.title, tt.description as task_desc FROM task_assignment ta
                                  JOIN task_template tt ON ta.template_id=tt.id WHERE ta.coachee_id=%s ORDER BY ta.created_at"""),
                     ("tracking", "SELECT * FROM tracking_log WHERE coachee_id=%s ORDER BY created_at"),
                     ("notes", "SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at"),
                     ("acknowledgements", "SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at")]:
        c.execute(q, (cid,))
        data[table] = [dict(r) for r in c.fetchall()]
    from flask import Response
    return Response(json.dumps(data, default=str, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=my_data_{cid}.json"})


@app.route("/coach/coachee/<int:cid>/reset-password", methods=["POST"])
@login_required("coach")
def reset_coachee_password(cid):
    c = db().cursor()
    new_pw = request.form["new_password"]
    c.execute("UPDATE coachee SET password_hash=%s WHERE id=%s AND coach_id=%s", (_hash(new_pw), cid, session["user_id"]))
    _audit(f"reset_password coachee={cid}")
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/coach/template/<int:tid>/edit", methods=["POST"])
@login_required("coach")
def edit_template(tid):
    c = db().cursor()
    c.execute("""UPDATE task_template SET title=%s, description=%s, category=%s, difficulty=%s,
                 recur_days=%s, recur_approx=%s, in_library=%s
                 WHERE id=%s AND coach_id=%s""",
              (request.form["title"], request.form.get("description", ""),
               request.form.get("category", "mental"), request.form.get("difficulty", "medium"),
               int(request.form.get("recur_days") or 0) or None,
               1 if request.form.get("recur_approx") else 0,
               1 if request.form.get("in_library") else 0,
               tid, session["user_id"]))
    return redirect(url_for("manage_tasks"))


@app.route("/coach/template/<int:tid>/delete", methods=["POST"])
@login_required("coach")
def delete_template(tid):
    c = db().cursor()
    c.execute("DELETE FROM task_template WHERE id=%s AND coach_id=%s", (tid, session["user_id"]))
    return redirect(url_for("manage_tasks"))


@app.route("/coach/voice/<int:cid>", methods=["POST"])
@login_required("coach")
def coach_voice_note(cid):
    c = db().cursor()
    audio = request.form.get("audio_data")
    if audio and audio.startswith("data:audio"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/voice_{cid}_{int(datetime.now().timestamp())}.webm"
        with open(path, "wb") as f:
            f.write(base64.b64decode(audio.split(",", 1)[1]))
        dur = int(request.form.get("duration", 0))
        c.execute("INSERT INTO voice_note (coachee_id, author_role, file_path, duration_sec) VALUES (%s,'coach',%s,%s)", (cid, path, dur))
    return redirect(url_for("coach_view_coachee", cid=cid))


@app.route("/me/voice", methods=["POST"])
@login_required("coachee")
def coachee_voice_note():
    c = db().cursor()
    audio = request.form.get("audio_data")
    if audio and audio.startswith("data:audio"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/voice_{session['user_id']}_{int(datetime.now().timestamp())}.webm"
        with open(path, "wb") as f:
            f.write(base64.b64decode(audio.split(",", 1)[1]))
        dur = int(request.form.get("duration", 0))
        c.execute("INSERT INTO voice_note (coachee_id, author_role, file_path, duration_sec) VALUES (%s,'coachee',%s,%s)", (session["user_id"], path, dur))
    return redirect(url_for("coachee_dashboard"))


@app.route("/voice/<int:vid>")
def serve_voice(vid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    c = db().cursor()
    c.execute("SELECT file_path, coachee_id FROM voice_note WHERE id=%s", (vid,))
    row = c.fetchone()
    if not row:
        return "Not found", 404
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        return "Forbidden", 403
    try:
        with open(row["file_path"], "rb") as f:
            data = f.read()
        from flask import Response
        return Response(data, mimetype="audio/webm")
    except FileNotFoundError:
        return "Not found", 404


@app.route("/me/goal", methods=["POST"])
@login_required("coachee")
def propose_goal():
    c = db().cursor()
    c.execute("INSERT INTO goal (coachee_id, title, description) VALUES (%s,%s,%s)",
              (session["user_id"], request.form["title"], request.form.get("description", "")))
    return redirect(url_for("coachee_dashboard"))


@app.route("/coach/goal/<int:gid>", methods=["POST"])
@login_required("coach")
def review_goal(gid):
    c = db().cursor()
    c.execute("""UPDATE goal SET status=%s, coach_notes=%s
                 WHERE id=%s AND coachee_id IN (SELECT id FROM coachee WHERE coach_id=%s)""",
              (request.form["status"], request.form.get("coach_notes", ""), gid, session["user_id"]))
    return redirect(request.referrer or url_for("coach_dashboard"))


@app.route("/me/journal", methods=["POST"])
@login_required("coachee")
def add_journal():
    c = db().cursor()
    visible = 1 if request.form.get("visible_to_coach") else 0
    c.execute("INSERT INTO journal (coachee_id, content, visible_to_coach) VALUES (%s,%s,%s)",
              (session["user_id"], request.form["content"], visible))
    return redirect(url_for("coachee_dashboard"))


@app.route("/me/progress-photo", methods=["POST"])
@login_required("coachee")
def add_progress_photo():
    img_data = request.form.get("photo_data")
    if img_data and img_data.startswith("data:image"):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        path = f"{ATTACHMENTS_DIR}/progress_{session['user_id']}_{int(datetime.now().timestamp())}.jpg"
        with open(path, "wb") as f:
            f.write(base64.b64decode(img_data.split(",", 1)[1]))
        c = db().cursor()
        c.execute("INSERT INTO progress_photo (coachee_id, file_path, caption) VALUES (%s,%s,%s)",
                  (session["user_id"], path, request.form.get("caption", "")))
    return redirect(url_for("coachee_dashboard"))


@app.route("/progress-photo/<int:pid>")
def serve_progress_photo(pid):
    if "user_id" not in session:
        return redirect(url_for("login"))
    c = db().cursor()
    c.execute("SELECT file_path, coachee_id FROM progress_photo WHERE id=%s", (pid,))
    row = c.fetchone()
    if not row:
        return "Not found", 404
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        return "Forbidden", 403
    try:
        with open(row["file_path"], "rb") as f:
            data = f.read()
        from flask import Response
        return Response(data, mimetype="image/jpeg")
    except FileNotFoundError:
        return "Not found", 404


@app.route("/coach/coachee/<int:cid>/heatmap")
@login_required("coach")
def compliance_heatmap(cid):
    c = db().cursor()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        return "Not found", 404
    c.execute("""SELECT due_date, status FROM task_assignment WHERE coachee_id=%s AND due_date IS NOT NULL
                 AND due_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) ORDER BY due_date""", (cid,))
    tasks = c.fetchall()
    # build day map
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


@app.route("/coach/coachee/<int:cid>/categories")
@login_required("coach")
def category_breakdown(cid):
    c = db().cursor()
    c.execute("SELECT name FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    c.execute("""SELECT tt.category, COUNT(*) as total,
                 SUM(ta.status='completed') as completed,
                 SUM(ta.status='missed') as missed,
                 AVG(FIELD(ta.grade,'A','B','C','D','E','F')) as avg_g
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s GROUP BY tt.category""", (cid,))
    cats = c.fetchall()
    for cat in cats:
        cat["avg_grade"] = chr(64 + round(cat["avg_g"])) if cat["avg_g"] else "—"
    return render_template_string(_tpl("categories.html"), coachee=coachee, cats=cats)


# ── Admin ──

@app.route("/admin")
@admin_required
def admin_dashboard():
    c = db().cursor()
    c.execute("SELECT id, username, name, status, is_admin, created_at FROM coach ORDER BY name")
    coaches = c.fetchall()
    for co in coaches:
        c.execute("SELECT COUNT(*) as cnt FROM coachee WHERE coach_id=%s", (co["id"],))
        co["coachee_count"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id WHERE ce.coach_id=%s", (co["id"],))
        co["task_count"] = c.fetchone()["cnt"]
        c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id
                     WHERE ce.coach_id=%s AND ta.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)""", (co["id"],))
        co["tasks_7d"] = c.fetchone()["cnt"]
        c.execute("""SELECT COUNT(*) as cnt FROM note n JOIN coachee ce ON n.coachee_id=ce.id
                     WHERE ce.coach_id=%s AND n.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)""", (co["id"],))
        co["notes_7d"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM audit_log WHERE user_id=%s AND role='coach' AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)", (co["id"],))
        co["logins_7d"] = c.fetchone()["cnt"]
    return render_template_string(_tpl("admin_dashboard.html"), coaches=coaches)


@app.route("/admin/coach/add", methods=["GET", "POST"])
@admin_required
def admin_add_coach():
    if request.method == "POST":
        c = db().cursor()
        c.execute("INSERT INTO coach (username, password_hash, name, timezone) VALUES (%s,%s,%s,%s)",
                  (request.form["username"], _hash(request.form["password"]), request.form["name"],
                   request.form.get("timezone", "Europe/London")))
        _audit(f"admin_add_coach {request.form['username']}")
        return redirect(url_for("admin_dashboard"))
    return render_template_string(_tpl("admin_add_coach.html"))


@app.route("/admin/coach/<int:coid>/freeze", methods=["POST"])
@admin_required
def admin_freeze_coach(coid):
    c = db().cursor()
    c.execute("UPDATE coach SET status=IF(status='active','frozen','active') WHERE id=%s AND is_admin=0", (coid,))
    _audit(f"admin_toggle_freeze coach={coid}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/coach/<int:coid>/delete", methods=["POST"])
@admin_required
def admin_delete_coach(coid):
    c = db().cursor()
    # prevent deleting admin or self
    c.execute("SELECT is_admin FROM coach WHERE id=%s", (coid,))
    row = c.fetchone()
    if row and row["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    # delete cascade: coachee data then coachees then coach
    c.execute("SELECT id FROM coachee WHERE coach_id=%s", (coid,))
    for ce in c.fetchall():
        for tbl in ("checkin", "tracking_log", "note", "acknowledgement", "mental_conditioning_response",
                     "task_assignment", "psychological_profile", "contract_history", "goal", "journal",
                     "voice_note", "progress_photo", "weekly_summary"):
            try:
                c.execute(f"DELETE FROM {tbl} WHERE coachee_id=%s", (ce["id"],))
            except Exception:
                pass
        c.execute("DELETE FROM coachee WHERE id=%s", (ce["id"],))
    for tbl in ("task_template", "mental_conditioning"):
        try:
            c.execute(f"DELETE FROM {tbl} WHERE coach_id=%s", (coid,))
        except Exception:
            pass
    c.execute("DELETE FROM coach WHERE id=%s AND is_admin=0", (coid,))
    _audit(f"admin_delete_coach {coid}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/coach/<int:coid>/reset-password", methods=["POST"])
@admin_required
def admin_reset_coach_password(coid):
    c = db().cursor()
    c.execute("UPDATE coach SET password_hash=%s WHERE id=%s", (_hash(request.form["new_password"]), coid))
    _audit(f"admin_reset_password coach={coid}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/support")
@admin_required
def admin_support():
    c = db().cursor()
    c.execute("""SELECT sm.*, co.name as coach_name, co.username
                 FROM support_message sm JOIN coach co ON sm.coach_id=co.id
                 ORDER BY FIELD(sm.status,'open','resolved'), sm.created_at DESC LIMIT 50""")
    messages = c.fetchall()
    return render_template_string(_tpl("admin_support.html"), messages=messages)


@app.route("/admin/support/<int:mid>/reply", methods=["POST"])
@admin_required
def admin_reply_support(mid):
    c = db().cursor()
    c.execute("UPDATE support_message SET admin_reply=%s, status=%s WHERE id=%s",
              (request.form["reply"], request.form.get("status", "resolved"), mid))
    return redirect(url_for("admin_support"))


# ── Bootstrap ──

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"DB init warning: {e}")
