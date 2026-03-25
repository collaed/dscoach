import os
import hashlib
import secrets
from functools import wraps
from datetime import date, datetime, timedelta

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
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND DATE(ta.created_at)=CURDATE() AND tt.is_reserve=0""", (coachee_id,))
    if c.fetchone()["cnt"] > 0:
        return
    # already got a reserve today?
    c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND DATE(ta.created_at)=CURDATE() AND tt.is_reserve=1""", (coachee_id,))
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
        today = date.today().isoformat()
        vis = f"{today} {cc['task_unveil_time']}" if cc["task_unveil_time"] else None
        frz = f"{today} {cc['task_freeze_time']}" if cc["task_freeze_time"] else None
        c.execute("""INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after)
                     VALUES (%s,%s,%s,%s,%s)""", (row["id"], coachee_id, today, vis, frz))


def _freeze_overdue(coachee_id):
    """Mark pending tasks as missed if past freeze time."""
    c = db().cursor()
    c.execute("""UPDATE task_assignment SET status='missed'
                 WHERE coachee_id=%s AND status='pending' AND frozen_after IS NOT NULL AND frozen_after < NOW()""",
              (coachee_id,))


def _visible_tasks(coachee_id):
    """Get tasks that are visible (past unveil time) and not yet frozen/completed."""
    c = db().cursor()
    c.execute("""SELECT ta.*, tt.title, tt.description as task_desc, tt.category
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.status='pending'
                 AND (ta.visible_after IS NULL OR ta.visible_after <= NOW())
                 AND (ta.frozen_after IS NULL OR ta.frozen_after > NOW())
                 ORDER BY ta.due_date""", (coachee_id,))
    return c.fetchall()


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
        c.execute("SELECT id, name FROM coach WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            session.update(user_id=row["id"], role="coach", name=row["name"])
            return redirect(url_for("coach_dashboard"))
        c.execute("SELECT id, name, coach_id FROM coachee WHERE username=%s AND password_hash=%s", (username, pw))
        row = c.fetchone()
        if row:
            session.update(user_id=row["id"], role="coachee", name=row["name"], coach_id=row["coach_id"])
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
        c.execute("INSERT INTO coach (username, password_hash, name) VALUES (%s,%s,%s)",
                  (request.form["username"], _hash(request.form["password"]), request.form["name"]))
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
        c.execute("""SELECT COUNT(*) as cnt FROM task_assignment ta
                     JOIN task_template tt ON ta.template_id=tt.id
                     WHERE ta.coachee_id=%s AND ta.status='pending'""", (cc["id"],))
        cc["pending_tasks"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s AND DATE(created_at)=CURDATE()", (cc["id"],))
        cc["checkins_today"] = c.fetchone()["cnt"]
    return render_template_string(_tpl("coach_dashboard.html"), coachees=coachees)


@app.route("/coach/coachee/add", methods=["GET", "POST"])
@login_required("coach")
def add_coachee():
    if request.method == "POST":
        c = db().cursor()
        c.execute("""INSERT INTO coachee (username, password_hash, name, coach_id, contract_text, safe_word,
                     task_unveil_time, task_freeze_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (request.form["username"], _hash(request.form["password"]), request.form["name"],
                   session["user_id"], request.form.get("contract", ""), request.form.get("safe_word", "RED"),
                   request.form.get("task_unveil_time", "08:00"), request.form.get("task_freeze_time", "22:00")))
        return redirect(url_for("coach_dashboard"))
    return render_template_string(_tpl("add_coachee.html"))


@app.route("/coach/coachee/<int:cid>")
@login_required("coach")
def coach_view_coachee(cid):
    c = db().cursor()
    c.execute("SELECT * FROM coachee WHERE id=%s AND coach_id=%s", (cid, session["user_id"]))
    coachee = c.fetchone()
    if not coachee:
        return "Not found", 404
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
    return render_template_string(_tpl("coach_view_coachee.html"),
                                 coachee=coachee, tasks=tasks, checkins=checkins,
                                 acks=acks, logs=logs, notes=notes, conditioning=conditioning)


@app.route("/coach/coachee/<int:cid>/edit", methods=["POST"])
@login_required("coach")
def edit_coachee(cid):
    c = db().cursor()
    c.execute("""UPDATE coachee SET contract_text=%s, safe_word=%s, task_unveil_time=%s, task_freeze_time=%s
                 WHERE id=%s AND coach_id=%s""",
              (request.form.get("contract", ""), request.form.get("safe_word", "RED"),
               request.form.get("task_unveil_time", "08:00"), request.form.get("task_freeze_time", "22:00"),
               cid, session["user_id"]))
    return redirect(url_for("coach_view_coachee", cid=cid))


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
    now = datetime.now().time()
    if coachee["task_unveil_time"] and now >= coachee["task_unveil_time"]:
        _auto_assign_reserves(cid, coachee["coach_id"])

    _freeze_overdue(cid)

    tasks = _visible_tasks(cid)

    c.execute("""SELECT mc.* FROM mental_conditioning mc
                 WHERE (mc.target='all' OR mc.coachee_id=%s) AND mc.prompt_date=CURDATE()
                 AND mc.id NOT IN (SELECT conditioning_id FROM mental_conditioning_response WHERE coachee_id=%s)""", (cid, cid))
    conditioning = c.fetchall()
    c.execute("SELECT * FROM checkin WHERE coachee_id=%s AND DATE(created_at)=CURDATE() ORDER BY created_at", (cid,))
    today_checkins = c.fetchall()
    c.execute("SELECT * FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    acks = c.fetchall()
    c.execute("SELECT * FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 10", (cid,))
    notes = c.fetchall()
    c.execute("SELECT * FROM tracking_log WHERE coachee_id=%s AND DATE(created_at)=CURDATE() ORDER BY created_at", (cid,))
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

    return render_template_string(_tpl("coachee_dashboard.html"),
                                 coachee=coachee, tasks=tasks, conditioning=conditioning,
                                 today_checkins=today_checkins, acks=acks, notes=notes,
                                 today_tracking=today_tracking, badges=badges)


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
    # check not frozen
    c.execute("SELECT frozen_after FROM task_assignment WHERE id=%s AND coachee_id=%s", (tid, session["user_id"]))
    row = c.fetchone()
    if row and row["frozen_after"] and datetime.now() > row["frozen_after"]:
        return redirect(url_for("coachee_dashboard"))  # too late
    c.execute("UPDATE task_assignment SET status='completed', response=%s, responded_at=NOW() WHERE id=%s AND coachee_id=%s",
              (request.form["response"], tid, session["user_id"]))
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
    init_db()
