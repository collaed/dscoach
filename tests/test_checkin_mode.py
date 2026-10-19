"""Tests for R40: check-in modes (optional/rewarded/required)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="checkinsub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Checkin Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM coachee WHERE username=:u"), {"u": username}).scalar()


def test_default_checkin_mode_is_optional(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT checkin_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert mode == "optional"


def test_coach_can_set_checkin_mode(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    resp = client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "required"})
    assert resp.status_code == 302
    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT checkin_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert mode == "required"


def test_invalid_checkin_mode_falls_back_to_optional(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "bogus"})
    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT checkin_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert mode == "optional"


def test_non_owning_coach_cannot_set_checkin_mode(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach3", "password": "pass123", "name": "Other Coach 3", "timezone": "UTC"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "othercoach3", "password": "pass123"})

    resp = client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "required"})
    assert resp.status_code == 404


def test_rewarded_mode_awards_points_on_checkin(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "rewarded"})
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET features=:f WHERE id=1"), {"f": '{"checkin_bonus": 3}'})
    client.get("/logout")

    client.post("/login", data={"username": "checkinsub", "password": "pass123"})
    client.post("/me/checkin", data={"checkin_type": "morning", "content": "feeling good"})

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT points FROM score_log WHERE coachee_id=:c AND reason='checkin'"), {"c": cid}
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3


def test_optional_mode_awards_no_points_on_checkin(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET features=:f WHERE id=1"), {"f": '{"checkin_bonus": 3}'})
    client.get("/logout")

    client.post("/login", data={"username": "checkinsub", "password": "pass123"})
    client.post("/me/checkin", data={"checkin_type": "morning", "content": "feeling good"})

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='checkin'"), {"c": cid}
        ).fetchall()
    assert len(rows) == 0


def test_required_mode_penalizes_missed_day_once(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "required"})
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET features=:f WHERE id=1"), {"f": '{"checkin_miss_penalty": 2}'})
    client.get("/logout")

    client.post("/login", data={"username": "checkinsub", "password": "pass123"})
    client.get("/me")  # yesterday had zero check-ins -> should penalize once
    client.get("/me")  # second load same day must not double-penalize

    with engine.connect() as conn:
        rows = (
            engine.connect()
            .execute(text("SELECT points FROM score_log WHERE coachee_id=:c AND reason='checkin_missed'"), {"c": cid})
            .fetchall()
        )
        strikes = conn.execute(text("SELECT strikes FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert len(rows) == 1
    assert rows[0][0] == -2
    assert strikes == 1


def test_required_mode_skips_penalty_when_checkin_happened_yesterday(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "required"})
    client.get("/logout")

    engine = get_engine()
    tz = ZoneInfo("UTC")
    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO checkin (coachee_id, checkin_type, content, created_at) VALUES (:c,'morning','ok',:ts)"),
            {"c": cid, "ts": yesterday},
        )

    client.post("/login", data={"username": "checkinsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='checkin_missed'"), {"c": cid}
        ).fetchall()
    assert len(rows) == 0


def test_required_mode_skipped_while_unavailable(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/checkin-mode", data={"mode": "required"})
    client.post(f"/coach/coachee/{cid}/unavailable", data={"note": "away"})
    client.get("/logout")

    client.post("/login", data={"username": "checkinsub", "password": "pass123"})
    client.get("/me")

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='checkin_missed'"), {"c": cid}
        ).fetchall()
    assert len(rows) == 0
