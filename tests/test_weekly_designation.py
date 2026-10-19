"""Tests for R43: weekly status designation (GREEN/YELLOW/RED)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="designub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Desig Sub",
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


def _this_monday():
    tz = ZoneInfo("UTC")
    today = datetime.now(tz).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def test_coach_can_set_weekly_designation(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    resp = client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "green"})
    assert resp.status_code == 302

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT designation, week_start FROM weekly_summary WHERE coachee_id=:c"), {"c": cid}
        ).fetchone()
    assert row[0] == "green"
    assert str(row[1]) == _this_monday()


def test_setting_designation_twice_updates_not_duplicates(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "green"})
    client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "red"})

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT designation FROM weekly_summary WHERE coachee_id=:c"), {"c": cid}).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "red"


def test_invalid_designation_value_is_rejected(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "purple"})

    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM weekly_summary WHERE coachee_id=:c"), {"c": cid}).scalar()
    assert count == 0


def test_non_owning_coach_cannot_set_designation(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach8", "password": "pass123", "name": "Other Coach 8", "timezone": "UTC"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "othercoach8", "password": "pass123"})

    resp = client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "green"})
    assert resp.status_code == 404


def test_coachee_dashboard_shows_current_designation(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/weekly-designation", data={"designation": "yellow"})
    client.get("/logout")

    client.post("/login", data={"username": "designub", "password": "pass123"})
    resp = client.get("/me")
    assert b"YELLOW" in resp.data


def test_coachee_dashboard_shows_nothing_when_undesignated(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    _add_coachee(client)
    client.get("/logout")

    client.post("/login", data={"username": "designub", "password": "pass123"})
    resp = client.get("/me")
    assert b"This week:" not in resp.data


def test_weekly_summary_screen_renders_a_working_designation_form_action(client):
    """Regression test: the weekly_summary() route's SELECT originally fetched only
    `name, timezone` (not `id`), so the rendered page's {{ coachee.id }} in the
    designation form's action URL was empty - a POST-based API test can't catch
    this since it bypasses the template entirely, found only by driving the real
    rendered form (caught via a Playwright walkthrough).
    """
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    resp = client.get(f"/coach/coachee/{cid}/summary")
    assert f'action="/coach/coachee/{cid}/weekly-designation"'.encode() in resp.data


def test_weekly_summary_screen_shows_history(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO weekly_summary (coachee_id, week_start, designation) VALUES (:c, '2020-01-06', 'red')"),
            {"c": cid},
        )
    resp = client.get(f"/coach/coachee/{cid}/summary")
    assert resp.status_code == 200
    assert b"week of 2020-01-06" in resp.data
    assert b"Not yet designated" in resp.data
