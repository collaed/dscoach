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
    """PURPOSE: Return True if the coachee's status is paused or stopped (in freeze state).
    CALLED BY / SCREEN: coachee/coach route + background detection checks that gate task assignment
    and penalties — affects /me dashboard and coach coachee views.
    WHEN: whenever freeze state must be checked (task assignment, dashboard load, detection jobs)."""
    from repos.coachee_repo import get_status
    status = get_status(coachee_id)
    return status in ("paused", "stopped")


def activate(coachee_id: int, initiated_by: str = "coachee", use_safeword: bool = False) -> str:
    """PURPOSE: Set a coachee's status to paused (or stopped when safeword used) and audit it;
    returns the new status.
    CALLED BY / SCREEN: routes_coachee.py boundaries handler (POST /me safeword/pause) — coachee
    Boundaries screen; also invokable by coach.
    WHEN: on coachee triggering pause/safeword (form submit).

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
    """PURPOSE: Reactivate a frozen coachee (status='active'), either extending pending task due
    dates or cancelling them, and audit it. Coach-only.
    CALLED BY / SCREEN: coach reactivation handler (POST on coach coachee-management screen);
    freeze-service API. No live route caller found in src/ via grep (service entry point).
    WHEN: on coach reactivating a paused/stopped coachee (form submit).

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
    """PURPOSE: Return {status, coachee_id, name} for a frozen coachee, or None if active/missing.
    CALLED BY / SCREEN: freeze-status display for coach coachee views / coachee Boundaries screen
    (service accessor). No live route caller found in src/ via grep (service entry point).
    WHEN: on rendering freeze/boundaries status for a coachee."""
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
