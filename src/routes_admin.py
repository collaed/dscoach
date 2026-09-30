"""Admin blueprint: all /admin/* routes."""

from datetime import datetime, timedelta

from flask import Blueprint, redirect, render_template_string, request, url_for

from auth import admin_required
from helpers import _audit, _hash_password, _tpl, db, utcnow

bp = Blueprint("admin", __name__)



@bp.route("/admin")
@admin_required
def admin_dashboard():
    """PURPOSE: Build the admin overview — list all coaches with per-coach counts (coachees, tasks, 7-day tasks/notes/logins).
    CALLED BY: Route GET /admin — renders admin_dashboard.html, the admin home screen (guarded by @admin_required).
    WHEN: On loading the admin dashboard."""
    c = db()
    c.execute("SELECT id, username, name, status, is_admin, created_at FROM coach ORDER BY name")
    coaches = c.fetchall()
    seven_days_ago = (utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    for co in coaches:
        c.execute("SELECT COUNT(*) as cnt FROM coachee WHERE coach_id=%s", (co["id"],))
        co["coachee_count"] = c.fetchone()["cnt"]
        c.execute(
            "SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id WHERE ce.coach_id=%s",
            (co["id"],),
        )
        co["task_count"] = c.fetchone()["cnt"]
        c.execute(
            """SELECT COUNT(*) as cnt FROM task_assignment ta JOIN coachee ce ON ta.coachee_id=ce.id
                     WHERE ce.coach_id=%s AND ta.created_at >= %s""",
            (co["id"], seven_days_ago),
        )
        co["tasks_7d"] = c.fetchone()["cnt"]
        c.execute(
            """SELECT COUNT(*) as cnt FROM note n JOIN coachee ce ON n.coachee_id=ce.id
                     WHERE ce.coach_id=%s AND n.created_at >= %s""",
            (co["id"], seven_days_ago),
        )
        co["notes_7d"] = c.fetchone()["cnt"]
        c.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE user_id=%s AND role='coach' AND created_at >= %s",
            (co["id"], seven_days_ago),
        )
        co["logins_7d"] = c.fetchone()["cnt"]
    return render_template_string(_tpl("admin_dashboard.html"), coaches=coaches)


@bp.route("/admin/coach/add", methods=["GET", "POST"])
@admin_required
def admin_add_coach():
    """PURPOSE: Create a new coach account from the admin panel (hashed password, timezone).
    CALLED BY: Route GET/POST /admin/coach/add — renders admin_add_coach.html form; POST inserts the coach then redirects to admin dashboard.
    WHEN: On opening the add-coach form (GET) or submitting it (POST)."""
    if request.method == "POST":
        c = db()
        c.execute(
            "INSERT INTO coach (username, password_hash, name, timezone) VALUES (%s,%s,%s,%s)",
            (
                request.form["username"],
                _hash_password(request.form["password"]),
                request.form["name"],
                request.form.get("timezone", "Europe/London"),
            ),
        )
        _audit(f"admin_add_coach {request.form['username']}")
        return redirect(url_for("admin.admin_dashboard"))
    return render_template_string(_tpl("admin_add_coach.html"))


@bp.route("/admin/coach/<int:coid>/freeze", methods=["POST"])
@admin_required
def admin_freeze_coach(coid):
    """PURPOSE: Toggle a non-admin coach's status between active and frozen (frozen coaches and their coachees cannot log in).
    CALLED BY: Route POST /admin/coach/<coid>/freeze — freeze/unfreeze button on the admin dashboard; redirects back to it.
    WHEN: On clicking freeze/unfreeze for a coach."""
    c = db()
    c.execute(
        "UPDATE coach SET status=CASE WHEN status='active' THEN 'frozen' ELSE 'active' END WHERE id=%s AND is_admin=0",
        (coid,),
    )
    _audit(f"admin_toggle_freeze coach={coid}")
    return redirect(url_for("admin.admin_dashboard"))



@bp.route("/admin/coach/<int:coid>/delete", methods=["POST"])
@admin_required
def admin_delete_coach(coid):
    """PURPOSE: Permanently delete a non-admin coach and cascade-delete all their coachees' data across every dependent table.
    CALLED BY: Route POST /admin/coach/<coid>/delete — delete button on the admin dashboard; redirects back to it.
    WHEN: On confirming coach deletion."""
    c = db()
    # prevent deleting admin or self
    c.execute("SELECT is_admin FROM coach WHERE id=%s", (coid,))
    row = c.fetchone()
    if row and row["is_admin"]:
        return redirect(url_for("admin.admin_dashboard"))
    # delete cascade: coachee data then coachees then coach
    c.execute("SELECT id FROM coachee WHERE coach_id=%s", (coid,))
    for ce in c.fetchall():
        for tbl in (
            "checkin",
            "tracking_log",
            "note",
            "acknowledgement",
            "mental_conditioning_response",
            "task_assignment",
            "psychological_profile",
            "contract_history",
            "goal",
            "journal",
            "voice_note",
            "progress_photo",
            "weekly_summary",
        ):
            try:
                c.execute(f"DELETE FROM {tbl} WHERE coachee_id=%s", (ce["id"],))  # nosec B608 - tbl from hardcoded list
            except Exception:
                pass
        c.execute("DELETE FROM coachee WHERE id=%s", (ce["id"],))
    for tbl in ("task_template", "mental_conditioning"):
        try:
            c.execute(f"DELETE FROM {tbl} WHERE coach_id=%s", (coid,))  # nosec B608 - tbl from hardcoded list
        except Exception:
            pass
    c.execute("DELETE FROM coach WHERE id=%s AND is_admin=0", (coid,))
    _audit(f"admin_delete_coach {coid}")
    return redirect(url_for("admin.admin_dashboard"))


@bp.route("/admin/coach/<int:coid>/reset-password", methods=["POST"])
@admin_required
def admin_reset_coach_password(coid):
    """PURPOSE: Reset a coach's password to an admin-supplied value (stored hashed).
    CALLED BY: Route POST /admin/coach/<coid>/reset-password — reset-password form on the admin dashboard; redirects back to it.
    WHEN: On submitting a coach password reset."""
    c = db()
    c.execute("UPDATE coach SET password_hash=%s WHERE id=%s", (_hash_password(request.form["new_password"]), coid))
    _audit(f"admin_reset_password coach={coid}")
    return redirect(url_for("admin.admin_dashboard"))


@bp.route("/admin/support")
@admin_required
def admin_support():
    """PURPOSE: List the 50 most recent coach→admin support tickets (open first), joined with the sending coach.
    CALLED BY: Route GET /admin/support — renders admin_support.html, the admin support-inbox screen.
    WHEN: On loading the admin support screen."""
    c = db()
    c.execute("""SELECT sm.*, co.name as coach_name, co.username
                 FROM support_message sm JOIN coach co ON sm.coach_id=co.id
                 ORDER BY CASE sm.status WHEN 'open' THEN 1 ELSE 2 END, sm.created_at DESC LIMIT 50""")
    messages = c.fetchall()
    return render_template_string(_tpl("admin_support.html"), messages=messages)


@bp.route("/admin/support/<int:mid>/reply", methods=["POST"])
@admin_required
def admin_reply_support(mid):
    """PURPOSE: Save an admin's reply to a support ticket and update its status (default resolved).
    CALLED BY: Route POST /admin/support/<mid>/reply — reply form on admin_support.html; redirects back to the support screen.
    WHEN: On submitting a support-ticket reply."""
    c = db()
    c.execute(
        "UPDATE support_message SET admin_reply=%s, status=%s WHERE id=%s",
        (request.form["reply"], request.form.get("status", "resolved"), mid),
    )
    return redirect(url_for("admin.admin_support"))
