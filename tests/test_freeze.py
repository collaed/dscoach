"""Unit tests for task freezing (_freeze_overdue logic)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _setup_with_overdue_tasks(client, num_overdue=2):
    """Create coachee with tasks that have frozen_after in the past."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "freezetest",
            "password": "pass123",
            "name": "Freeze Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )

    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    # Use UTC time since the coachee timezone is UTC
    tz = ZoneInfo("UTC")
    past = (datetime.now(tz) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(tz).strftime("%Y-%m-%d")

    with engine.begin() as conn:
        for i in range(num_overdue):
            conn.execute(
                text(
                    "INSERT INTO task_template (coach_id, title, description, recurrence, category) "
                    "VALUES (1, :title, '', 'once', 'physical')"
                ),
                {"title": f"Overdue {i}"},
            )
            tid = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()
            conn.execute(
                text(
                    "INSERT INTO task_assignment (template_id, coachee_id, due_date, status, frozen_after) "
                    "VALUES (:tid, 1, :due, 'pending', :frz)"
                ),
                {"tid": tid, "due": today, "frz": past},
            )

    client.get("/logout")


def _get_coachee_data():
    """Get coachee strikes and streak."""
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT strikes, current_streak FROM coachee WHERE id=1")).mappings().fetchone()
        return dict(row)


def _count_missed():
    """Count missed tasks for coachee id=1."""
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM task_assignment WHERE coachee_id=1 AND status='missed'")
        ).scalar()


def test_marks_pending_as_missed_after_freeze(client):
    """Past freeze time → status becomes 'missed'."""
    _setup_with_overdue_tasks(client, num_overdue=2)

    client.post("/login", data={"username": "freezetest", "password": "pass123"})
    client.get("/me")  # triggers _freeze_overdue

    assert _count_missed() == 2


def test_adds_strikes_on_miss(client):
    """2 missed tasks → strikes += 2."""
    _setup_with_overdue_tasks(client, num_overdue=3)

    client.post("/login", data={"username": "freezetest", "password": "pass123"})
    client.get("/me")

    data = _get_coachee_data()
    assert data["strikes"] == 3


def test_resets_streak_on_miss(client):
    """Any miss → current_streak = 0."""
    _setup_with_overdue_tasks(client, num_overdue=1)

    # Set a streak first
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET current_streak=5 WHERE id=1"))

    client.post("/login", data={"username": "freezetest", "password": "pass123"})
    client.get("/me")

    data = _get_coachee_data()
    assert data["current_streak"] == 0


def test_does_nothing_before_freeze_time(client):
    """Tasks with future frozen_after → no change."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "freezetest",
            "password": "pass123",
            "name": "Freeze Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )

    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    tz = ZoneInfo("UTC")
    future = (datetime.now(tz) + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(tz).strftime("%Y-%m-%d")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category) "
                "VALUES (1, 'Future Task', '', 'once', 'physical')"
            )
        )
        tid = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()
        conn.execute(
            text(
                "INSERT INTO task_assignment (template_id, coachee_id, due_date, status, frozen_after) "
                "VALUES (:tid, 1, :due, 'pending', :frz)"
            ),
            {"tid": tid, "due": today, "frz": future},
        )

    client.get("/logout")
    client.post("/login", data={"username": "freezetest", "password": "pass123"})
    client.get("/me")

    assert _count_missed() == 0
    data = _get_coachee_data()
    assert data["strikes"] == 0
