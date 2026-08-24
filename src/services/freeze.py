"""FreezeService: manages the freeze/safeword lifecycle.

Callable from routes (coachee triggers freeze, coach reactivates)
and from background jobs (detection engine checks freeze status).

Business rules:
- Both coachee and coach can activate a freeze.
- During freeze: no new tasks assigned, no penalties, no notifications.
- Only the coach can reactivate.
- On reactivation, coach chooses: extend pending task deadlines or cancel them.
"""

from helpers import db, utcnow


def is_frozen(coachee_id: int) -> bool:
    """Check if a coachee is in freeze state (paused or stopped)."""
    from repos.coachee_repo import get_status
    status = get_status(coachee_id)
    return status in ("paused", "stopped")


def activate(coachee_id: int, initiated_by: str = "coachee", use_safeword: bool = False) -> str:
    """Activate freeze for a coachee.

    Args:
        coachee_id: The coachee to freeze.
        initiated_by: "coachee" or "coach".
        use_safeword: If True, status becomes "stopped" (full stop). Otherwise "paused".

    Returns:
        The new status ("paused" or "stopped").
    """
    new_status = "stopped" if use_safeword else "paused"
    c = db()
    c.execute("UPDATE coachee SET status=%s WHERE id=%s", (new_status, coachee_id))

    # Audit
    from helpers import _audit
    try:
        _audit(f"freeze_activated:{initiated_by}", coachee_id, initiated_by)
    except Exception:
        pass  # Best-effort audit (may fail outside request context)

    return new_status


def deactivate(coachee_id: int, pending_action: str = "extend") -> None:
    """Reactivate a frozen coachee. Coach-only operation.

    Args:
        coachee_id: The coachee to reactivate.
        pending_action: "extend" (postpone due dates) or "cancel" (mark pending tasks as cancelled).
    """
    c = db()

    if pending_action == "cancel":
        # Cancel all pending tasks
        c.execute(
            "UPDATE task_assignment SET status='cancelled' WHERE coachee_id=%s AND status='pending'",
            (coachee_id,),
        )
    elif pending_action == "extend":
        # Extend due dates: add the number of days the coachee was frozen
        # For now, push all pending due_dates forward by 7 days (simple heuristic)
        # Future: track freeze_at timestamp and compute exact delta
        c.execute(
            "UPDATE task_assignment SET due_date = due_date + 7 WHERE coachee_id=%s AND status='pending' AND due_date IS NOT NULL",
            (coachee_id,),
        )

    # Reactivate
    c.execute("UPDATE coachee SET status='active' WHERE id=%s", (coachee_id,))

    # Audit
    from helpers import _audit
    try:
        _audit(f"freeze_deactivated:pending={pending_action}", coachee_id, "coach")
    except Exception:
        pass


def get_freeze_info(coachee_id: int) -> dict | None:
    """Get freeze status info for a coachee. Returns None if not frozen."""
    from repos.coachee_repo import get_by_id
    coachee = get_by_id(coachee_id)
    if not coachee:
        return None
    if coachee["status"] not in ("paused", "stopped"):
        return None
    return {
        "status": coachee["status"],
        "coachee_id": coachee_id,
        "name": coachee["name"],
    }
