"""Unit tests for streak system (_update_streak logic)."""

from datetime import date, timedelta


def _setup_coachee_with_tasks(client, due_date, statuses):
    """Helper: create coachee, tasks with given statuses on due_date."""
    # Login as coach
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    # Create coachee
    client.post(
        "/coach/coachee/add",
        data={
            "username": "streaktest",
            "password": "pass123",
            "name": "Streak Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "06:00",
            "task_freeze_time": "23:00",
            "timezone": "UTC",
        },
    )
    # Create task templates and assignments via direct DB
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        for i, status in enumerate(statuses):
            conn.execute(
                text(
                    "INSERT INTO task_template (coach_id, title, description, recurrence, category) "
                    "VALUES (:cid, :title, :desc, 'once', 'physical')"
                ),
                {"cid": 1, "title": f"Task {i}", "desc": ""},
            )
            tmpl_id = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()
            conn.execute(
                text(
                    "INSERT INTO task_assignment (template_id, coachee_id, due_date, status) "
                    "VALUES (:tid, :cid, :due, :status)"
                ),
                {"tid": tmpl_id, "cid": 1, "due": due_date, "status": status},
            )
    client.get("/logout")


def _get_coachee_streak(client):
    """Get current streak data for coachee id=1."""
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(text("SELECT current_streak, best_streak, last_streak_date FROM coachee WHERE id=1"))
            .mappings()
            .fetchone()
        )
        return dict(row) if row else None


def test_streak_increments_on_all_complete(client):
    """Yesterday's tasks all completed → streak +1."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _setup_coachee_with_tasks(client, yesterday, ["completed", "completed"])

    # Login as coachee and load dashboard (triggers _update_streak)
    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 1
    assert streak["best_streak"] == 1


def test_streak_resets_on_any_missed(client):
    """One missed task yesterday → streak resets to 0."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _setup_coachee_with_tasks(client, yesterday, ["completed", "missed"])

    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 0


def test_streak_no_tasks_yesterday_no_change(client):
    """No tasks assigned yesterday → streak unchanged (stays 0)."""
    # Create coachee but no tasks for yesterday
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "streaktest",
            "password": "pass123",
            "name": "Streak Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "06:00",
            "task_freeze_time": "23:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")

    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 0


def test_streak_idempotent_same_day(client):
    """Calling dashboard twice on same day doesn't double-count streak."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _setup_coachee_with_tasks(client, yesterday, ["completed"])

    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")
    client.get("/me")  # second load

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 1  # not 2


def test_best_streak_updates(client):
    """New streak exceeding best_streak → best updated."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _setup_coachee_with_tasks(client, yesterday, ["completed"])

    # Manually set current_streak to 5, best_streak to 5
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET current_streak=5, best_streak=5 WHERE id=1"))

    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 6
    assert streak["best_streak"] == 6


def test_best_streak_not_lowered(client):
    """If best_streak > current+1, best stays the same."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _setup_coachee_with_tasks(client, yesterday, ["completed"])

    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET current_streak=2, best_streak=10 WHERE id=1"))

    client.post("/login", data={"username": "streaktest", "password": "pass123"})
    client.get("/me")

    streak = _get_coachee_streak(client)
    assert streak["current_streak"] == 3
    assert streak["best_streak"] == 10  # unchanged
