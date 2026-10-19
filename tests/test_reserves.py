"""Unit tests for reserve task auto-assignment (_auto_assign_reserves)."""

from datetime import date


def _create_reserve_template(coach_id=1, title="Reserve Task"):
    """Insert a reserve task template directly."""
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, is_reserve) "
                "VALUES (:cid, :title, '', 'once', 'mental', 1)"
            ),
            {"cid": coach_id, "title": title},
        )
        return conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()


def _create_manual_task(coach_id, coachee_id, due_date):
    """Insert a manually assigned (non-reserve) task for today."""
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, is_reserve) "
                "VALUES (:cid, 'Manual Task', '', 'once', 'physical', 0)"
            ),
            {"cid": coach_id},
        )
        tid = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()
        conn.execute(
            text(
                "INSERT INTO task_assignment (template_id, coachee_id, due_date, status) "
                "VALUES (:tid, :cid, :due, 'pending')"
            ),
            {"tid": tid, "cid": coachee_id, "due": due_date},
        )


def _count_assignments(coachee_id, due_date):
    """Count task assignments for a coachee on a given date."""
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM task_assignment WHERE coachee_id=:cid AND due_date=:due"),
            {"cid": coachee_id, "due": due_date},
        ).scalar()


def _setup_coachee(client):
    """Create a coachee with early unveil time so reserves trigger."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "reservetest",
            "password": "pass123",
            "name": "Reserve Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    client.get("/logout")


def test_assigns_reserve_when_no_task_today(client):
    """Empty day + reserve template exists → one reserve assigned."""
    _setup_coachee(client)
    _create_reserve_template()

    client.post("/login", data={"username": "reservetest", "password": "pass123"})
    client.get("/me")  # triggers _auto_assign_reserves

    today = date.today().isoformat()
    assert _count_assignments(1, today) == 1


def test_skips_when_manual_task_exists(client):
    """Manual task present → no reserve assigned."""
    _setup_coachee(client)
    _create_reserve_template()
    today = date.today().isoformat()
    _create_manual_task(coach_id=1, coachee_id=1, due_date=today)

    client.post("/login", data={"username": "reservetest", "password": "pass123"})
    client.get("/me")

    # Should have exactly 1 (the manual task), not 2
    assert _count_assignments(1, today) == 1


def test_no_duplicate_reserve_assignment(client):
    """Calling dashboard twice doesn't double-assign reserves."""
    _setup_coachee(client)
    _create_reserve_template()

    client.post("/login", data={"username": "reservetest", "password": "pass123"})
    client.get("/me")
    client.get("/me")  # second load

    today = date.today().isoformat()
    assert _count_assignments(1, today) == 1


def test_no_reserve_if_recurring_assigned(client):
    """If a recurring task was auto-assigned today, reserve is skipped."""
    _setup_coachee(client)
    _create_reserve_template()

    # Create a recurring template that will auto-assign
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, is_reserve, recur_days) "
                "VALUES (1, 'Daily Recurring', '', 'daily', 'physical', 0, 1)"
            )
        )

    client.post("/login", data={"username": "reservetest", "password": "pass123"})
    client.get("/me")

    today = date.today().isoformat()
    # The recurring task should be assigned (first-time assignment), so reserve is skipped
    count = _count_assignments(1, today)
    assert count >= 1  # recurring assigned
    # Check that the reserve template was NOT used
    with engine.connect() as conn:
        reserve_assignments = conn.execute(
            text(
                "SELECT COUNT(*) FROM task_assignment ta "
                "JOIN task_template tt ON ta.template_id=tt.id "
                "WHERE ta.coachee_id=1 AND tt.is_reserve=1 AND ta.due_date=:due"
            ),
            {"due": today},
        ).scalar()
    assert reserve_assignments == 0
