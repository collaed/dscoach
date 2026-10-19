"""Repository for coachee-related SQL queries."""

from helpers import db


def get_by_id(coachee_id: int) -> dict | None:
    """PURPOSE: Fetch a full coachee row by ID as a dict, or None if absent.
    CALLED BY / SCREEN: services/freeze.get_freeze_info() — backs freeze/boundaries status on the
    coachee Boundaries screen and coach coachee views.
    WHEN: on freeze-info lookup for a coachee."""
    c = db()
    c.execute("SELECT * FROM coachee WHERE id=%s", (coachee_id,))
    row: dict | None = c.fetchone()
    return row


def get_status(coachee_id: int) -> str | None:
    """PURPOSE: Return a coachee's current status string (e.g. active/paused/stopped), or None.
    CALLED BY / SCREEN: services/freeze.is_frozen() — gates task assignment/penalties on /me and
    coach coachee views.
    WHEN: whenever freeze state is evaluated (dashboard load, task assignment, detection)."""
    c = db()
    c.execute("SELECT status FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    return row["status"] if row else None


def update_status(coachee_id: int, status: str) -> None:
    """PURPOSE: Set a coachee's status column.
    CALLED BY / SCREEN: repository accessor for coachee status changes; no live caller found in
    src/ via grep (freeze.py currently updates status via direct SQL). Serves coach/coachee screens.
    WHEN: intended on status-change actions (freeze/reactivate/admin updates)."""
    c = db()
    c.execute("UPDATE coachee SET status=%s WHERE id=%s", (status, coachee_id))


def get_active_coachees() -> list[dict]:
    """PURPOSE: Return all coachees whose status is 'active' as dicts.
    CALLED BY / SCREEN: repository accessor; no live caller found in src/ via grep. Intended for
    coach dashboard / background jobs iterating active coachees.
    WHEN: intended on dashboard load or scheduled jobs over active coachees."""
    c = db()
    c.execute("SELECT * FROM coachee WHERE status='active'")
    rows: list[dict] = c.fetchall()
    return rows


def get_pending_task_count(coachee_id: int) -> int:
    """PURPOSE: Count a coachee's task_assignment rows still in 'pending' status.
    CALLED BY / SCREEN: repository accessor; no live caller found in src/ via grep. Intended for
    coach dashboard tiles / coachee tasks screen pending badges.
    WHEN: intended on dashboard/tasks screen render."""
    c = db()
    c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='pending'", (coachee_id,))
    count: int = c.fetchone()["cnt"]
    return count
