import os
import hashlib
import secrets
import json
from functools import wraps
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, request, redirect, url_for, session, render_template_string, g
from db import get_db, init_db

app = Flask(__name__, template_folder="/src/templates", static_folder="/static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


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
    c.execute("SELECT timezone FROM coachee WHERE id=%s", (coachee_id,))
    tz = ZoneInfo((c.fetchone()["timezone"]) or "UTC")
    local_today = datetime.now(tz).date().isoformat()
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND DATE(ta.created_at)=%s AND tt.is_reserve=0""", (coachee_id, local_today))
    if c.fetchone()["cnt"] > 0:
        return
    # already got a reserve today?
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND DATE(ta.created_at)=%s AND tt.is_reserve=1""", (coachee_id, local_today))
    if c.fetchone()["cnt"] > 0:
        return
    # pick one reserve not yet assigned to this coachee
    c.execute("""SELECT tt.id FROM task_template tt
                 WHERE tt.coach_id=%s AND tt.is_reserve=1
                 AND tt.id NOT IN (SELECT template_id FROM task_assignment WHERE coachee_id=%s)
                 ORDER BY RAND() LIMIT 1""", (coach_id, coachee_id))
    row = c.fetchone()
    if row:
        c.execute("SELECT task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (coachee_id,))
        cc = c.fetchone()
        vis = f"{local_today} {cc['task_unveil_time']}" if cc["task_unveil_time"] else None
        frz = f"{local_today} {cc['task_freeze_time']}" if cc["task_freeze_time"] else None
        c.execute("""INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after)
                     VALUES (%s,%s,%s,%s,%s)""", (row["id"], coachee_id, local_today, vis, frz))


def _freeze_overdue(coachee_id, tz):
    """Mark pending tasks as missed if past freeze time, add strikes."""
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
        c.execute("UPDATE coachee SET strikes=strikes+%s WHERE id=%s", (missed, coachee_id))


def _visible_tasks(coachee_id, tz):
    """Get tasks that are visible (past unveil time) and not yet frozen/completed."""
    c = db().cursor()
    local_now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""SELECT ta.*, tt.title, tt.description as task_desc, tt.category
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.status='pending'
                 AND (ta.visible_after IS NULL OR ta.visible_after <= %s)
                 AND (ta.frozen_after IS NULL OR ta.frozen_after > %s)
                 ORDER BY ta.due_date""", (coachee_id, local_now, local_now))
    return c.fetchall()


GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

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
        c.execute("SELECT id, name, timezone, accent_color, bg_color, card_color FROM coach WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            session.update(user_id=row["id"], role="coach", name=row["name"],
                           timezone=row["timezone"] or "Europe/London",
                           accent=row["accent_color"] or "#e94560",
                           bg=row["bg_color"] or "#1a1a2e",
                           card=row["card_color"] or "#16213e")
            return redirect(url_for("coach_dashboard"))
        c.execute("SELECT id, name, coach_id, color_scheme, avatar FROM coachee WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            c.execute("SELECT accent_color, bg_color, card_color FROM coach WHERE id=%s", (row["coach_id"],))
            coach_brand = c.fetchone()
            session.update(user_id=row["id"], role="coachee", name=row["name"], coach_id=row["coach_id"],
                           accent=row["color_scheme"] or coach_brand["accent_color"] or "#e94560",
                           bg=coach_brand["bg_color"] or "#1a1a2e",
                           card=coach_brand["card_color"] or "#16213e",
                           avatar=row["avatar"] or "🐕")
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
        c.execute("INSERT INTO coach (username, password_hash, name, timezone) VALUES (%s,%s,%s,%s)",
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
        c.execute("SELECT AVG(FIELD(grade,'A','B','C','D','E','F')) as avg_g FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL", (cc["id"],))
        avg = c.fetchone()["avg_g"]
        cc["avg_grade"] = chr(64 + round(avg)) if avg else "—"
        cc["strikes"] = cc.get("strikes") or 0
        c.execute("SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s AND DATE(created_at)=%s", (cc["id"],
                  datetime.now(ZoneInfo(cc["timezone"] or "UTC")).date().isoformat()))
        cc["checkins_today"] = c.fetchone()["cnt"]
    return render_template_string(_tpl("coach_dashboard.html"), coachees=coachees)


@app.route("/coach/branding", methods=["GET", "POST"])
@login_required("coach")
def coach_branding():
    c = db().cursor()
    if request.method == "POST":
        import base64
        logo = None
        logo_data = request.form.get("logo_data")
        if logo_data and logo_data.startswith("data:image"):
            logo = base64.b64decode(logo_data.split(",", 1)[1])
        accent = request.form.get("accent_color", "#e94560")
        bg = request.form.get("bg_color", "#1a1a2e")
        card = request.form.get("card_color", "#16213e")
        tg_token = request.form.get("telegram_bot_token", "")
        if logo:
            c.execute("UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s, logo=%s WHERE id=%s",
                      (accent, bg, card, tg_token, logo, session["user_id"]))
        else:
            c.execute("UPDATE coach SET accent_color=%s, bg_color=%s, card_color=%s, telegram_bot_token=%s WHERE id=%s",
                      (accent, bg, card, tg_token, session["user_id"]))
        session.update(accent=accent, bg=bg, card=card)
        return redirect(url_for("coach_branding"))
    c.execute("SELECT accent_color, bg_color, card_color, telegram_bot_token, logo IS NOT NULL as has_logo FROM coach WHERE id=%s", (session["user_id"],))
    coach = c.fetchone()
    return render_template_string(_tpl("coach_branding.html"), coach=coach)


@app.route("/coach/logo")
def coach_logo():
    cid = request.args.get("id") or (session.get("coach_id") if session.get("role") == "coachee" else session.get("user_id"))
    if not cid:
        return "", 404
    c = db().cursor()
    c.execute("SELECT logo FROM coach WHERE id=%s", (cid,))
    row = c.fetchone()
    if not row or not row["logo"]:
        return "", 404
    from flask import Response
    return Response(row["logo"], mimetype="image/png")


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
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20", (cid,))
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
    # fetch coach telegram token
    c.execute("SELECT telegram_bot_token FROM coach WHERE id=%s", (session["user_id"],))
    tg_token = (c.fetchone() or {}).get("telegram_bot_token", "")
    return render_template_string(_tpl("coach_view_coachee.html"),
                                 coachee=coachee, tasks=tasks, checkins=checkins,
                                 acks=acks, logs=logs, notes=notes, conditioning=conditioning,
                                 profile_text=profile_text,
                                 coachee_context=coachee.get("context_text", ""),
                                 gemini_key=GEMINI_KEY, tg_token=tg_token or "",
                                 coach_tz=session.get("timezone", "Europe/London"))


@app.route("/coach/coachee/<int:cid>/edit", methods=["POST"])
@login_required("coach")
def edit_coachee(cid):
    c = db().cursor()
    c.execute("""UPDATE coachee SET contract_text=%s, safe_word=%s, task_unveil_time=%s, task_freeze_time=%s,
                 timezone=%s, avatar=%s, color_scheme=%s, telegram_chat_id=%s
                 WHERE id=%s AND coach_id=%s""",
              (request.form.get("contract", ""), request.form.get("safe_word", "RED"),
               request.form.get("task_unveil_time", "08:00"), request.form.get("task_freeze_time", "22:00"),
               request.form.get("timezone", "Europe/London"),
               request.form.get("avatar", "🐕"), request.form.get("color_scheme", "#e94560"),
               request.form.get("telegram_chat_id", ""),
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
    return render_template_string(_tpl("analyze.html"), gemini_key=GEMINI_KEY)


@app.route("/coach/tasks", methods=["GET", "POST"])
@login_required("coach")
def manage_tasks():
    c = db().cursor()
    if request.method == "POST":
        is_reserve = 1 if request.form.get("is_reserve") else 0
        c.execute("INSERT INTO task_template (coach_id, title, description, recurrence, category, is_reserve) VALUES (%s,%s,%s,%s,%s,%s)",
                  (session["user_id"], request.form["title"], request.form["description"],
                   request.form["recurrence"], request.form["category"], is_reserve))
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
    c.execute("SELECT attachment, coachee_id FROM task_assignment WHERE id=%s", (tid,))
    row = c.fetchone()
    if not row or not row["attachment"]:
        return "Not found", 404
    if session["role"] == "coachee" and row["coachee_id"] != session["user_id"]:
        return "Forbidden", 403
    from flask import Response
    return Response(row["attachment"], mimetype="image/jpeg")


@app.route("/coach/note/<int:cid>", methods=["POST"])
@login_required("coach")
def coach_add_note(cid):
    c = db().cursor()
    c.execute("INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
              (cid, request.form["content"]))
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
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    notes = c.fetchall()
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

    return render_template_string(_tpl("coachee_dashboard.html"),
                                 coachee=coachee, tasks=tasks, conditioning=conditioning,
                                 today_checkins=today_checkins, acks=acks, notes=notes,
                                 today_tracking=today_tracking, badges=badges,
                                 graded_tasks=graded_tasks)


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
    import base64
    attachment = None
    att_data = request.form.get("attachment_data")
    if att_data and att_data.startswith("data:image"):
        attachment = base64.b64decode(att_data.split(",", 1)[1])
    c.execute("""UPDATE task_assignment SET status='completed', response=%s, attachment=%s, responded_at=NOW()
                 WHERE id=%s AND coachee_id=%s""",
              (request.form["response"], attachment, tid, session["user_id"]))
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


# ── Bootstrap ──

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"DB init warning: {e}")
