"""Repository for coachee-related SQL queries."""

from helpers import db


def get_by_id(coachee_id: int) -> dict | None:
    """Fetch a coachee by ID. Returns dict or None."""
    c = db()
    c.execute("SELECT * FROM coachee WHERE id=%s", (coachee_id,))
    return c.fetchone()


def get_status(coachee_id: int) -> str | None:
    """Get the current status of a coachee."""
    c = db()
    c.execute("SELECT status FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    return row["status"] if row else None


def update_status(coachee_id: int, status: str) -> None:
    """Update the status of a coachee."""
    c = db()
    c.execute("UPDATE coachee SET status=%s WHERE id=%s", (status, coachee_id))


def get_active_coachees() -> list[dict]:
    """Get all active coachees (not paused, stopped, or frozen)."""
    c = db()
    c.execute("SELECT * FROM coachee WHERE status='active'")
    return c.fetchall()


def get_pending_task_count(coachee_id: int) -> int:
    """Count pending tasks for a coachee."""
    c = db()
    c.execute("SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND status='pending'", (coachee_id,))
    return c.fetchone()["cnt"]
