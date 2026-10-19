"""Tests for R18: automatic ritual-miss detection."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="ritualsub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Ritual Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM coachee WHERE username=:u"), {"u": username}).scalar()


def _yesterday_utc():
    return (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat()


def test_daily_ritual_with_no_log_is_marked_missed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM ritual_log WHERE coachee_id=:c AND completed_date=:d"),
            {"c": cid, "d": _yesterday_utc()},
        ).fetchone()
    assert row is not None
    assert row[0] == "missed"


def test_daily_ritual_already_completed_is_not_overwritten(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
        rid = conn.execute(text("SELECT id FROM ritual WHERE coachee_id=:c"), {"c": cid}).scalar()
        conn.execute(
            text(
                "INSERT INTO ritual_log (ritual_id, coachee_id, completed_date, status) "
                "VALUES (:r, :c, :d, 'completed')"
            ),
            {"r": rid, "c": cid, "d": _yesterday_utc()},
        )
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status FROM ritual_log WHERE coachee_id=:c AND completed_date=:d"),
            {"c": cid, "d": _yesterday_utc()},
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "completed"


def test_weekday_only_ritual_not_due_on_a_weekend_is_not_missed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    yesterday = datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Workday check-in', 'weekdays')"
            ),
            {"c": cid},
        )
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM ritual_log WHERE coachee_id=:c AND completed_date=:d"),
            {"c": cid, "d": yesterday.isoformat()},
        ).fetchone()
    if yesterday.weekday() < 5:
        assert row is not None and row[0] == "missed"
    else:
        assert row is None


def test_detection_is_idempotent_across_repeated_loads(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
        conn.execute(
            text(
                "INSERT INTO auto_rule (coach_id, name, trigger, action_type, action_template, active) "
                "VALUES (1, 'miss rule', 'ritual_missed', 'send_note', 'A ritual was missed.', 1)"
            )
        )
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")
    client.get("/me")
    client.get("/me")

    with engine.connect() as conn:
        log_count = conn.execute(
            text("SELECT COUNT(*) FROM ritual_log WHERE coachee_id=:c AND status='missed'"), {"c": cid}
        ).scalar()
        note_count = conn.execute(
            text("SELECT COUNT(*) FROM note WHERE coachee_id=:c AND content='A ritual was missed.'"), {"c": cid}
        ).scalar()
    assert log_count == 1
    assert note_count == 1


def test_ritual_missed_trigger_fires_configured_auto_rule(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
        conn.execute(
            text(
                "INSERT INTO auto_rule (coach_id, name, trigger, action_type, action_template, active) "
                "VALUES (1, 'miss rule', 'ritual_missed', 'send_note', 'Heads up: a ritual was missed.', 1)"
            )
        )
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        note = conn.execute(
            text("SELECT content FROM note WHERE coachee_id=:c AND author_role='coach'"), {"c": cid}
        ).fetchone()
    assert note is not None
    assert note[0] == "Heads up: a ritual was missed."


def test_ritual_miss_detection_skipped_while_unavailable(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
    client.post(f"/coach/coachee/{cid}/unavailable", data={"note": "away"})
    client.get("/logout")

    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        row = conn.execute(text("SELECT 1 FROM ritual_log WHERE coachee_id=:c"), {"c": cid}).fetchone()
    assert row is None


def test_missed_ritual_does_not_count_as_completed_today(client):
    """A row with status='missed' must never be mistaken for a completion."""
    from automation import _ritual_status_today

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
        rid = conn.execute(text("SELECT id FROM ritual WHERE coachee_id=:c"), {"c": cid}).scalar()
        today = datetime.now(ZoneInfo("UTC")).date().isoformat()
        conn.execute(
            text(
                "INSERT INTO ritual_log (ritual_id, coachee_id, completed_date, status) VALUES (:r, :c, :d, 'missed')"
            ),
            {"r": rid, "c": cid, "d": today},
        )

    with client.application.app_context():
        done = _ritual_status_today(cid, [{"id": rid}], today)
    assert rid not in done


def test_coach_dashboard_shows_rituals_missed_badge(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ritual (coach_id, coachee_id, name, schedule) VALUES (1, :c, 'Morning bow', 'daily')"),
            {"c": cid},
        )
    client.get("/logout")
    client.post("/login", data={"username": "ritualsub", "password": "pass123"})
    client.get("/me")  # triggers the miss detection for yesterday
    client.get("/logout")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.get("/coach")
    assert b"rituals missed" in resp.data
