"""Tests for R47: unavailability protocol (self-declared + coach-declared)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import get_engine
from sqlalchemy import text


def _add_coachee_with_overdue_task(client, username="unavailsub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Unavail Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    engine = get_engine()
    with engine.connect() as conn:
        cid = conn.execute(text("SELECT id FROM coachee WHERE username=:u"), {"u": username}).scalar()

    tz = ZoneInfo("UTC")
    past = (datetime.now(tz) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category) "
                "VALUES (1, 'Overdue', '', 'once', 'physical')"
            )
        )
        tmpl_id = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()
        conn.execute(
            text(
                "INSERT INTO task_assignment (template_id, coachee_id, due_date, status, frozen_after) "
                "VALUES (:t, :c, :due, 'pending', :frz)"
            ),
            {"t": tmpl_id, "c": cid, "due": today, "frz": past},
        )
    return cid


def test_coachee_can_declare_and_end_unavailability(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)
    client.get("/logout")

    client.post("/login", data={"username": "unavailsub", "password": "pass123"})
    resp = client.post("/me/unavailable", data={"until": "2099-01-01", "note": "traveling"})
    assert resp.status_code == 302

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT unavailable_since, unavailable_until, unavailable_note FROM coachee WHERE id=:c"), {"c": cid}
        ).fetchone()
    assert row[0] is not None
    assert str(row[1]) == "2099-01-01"
    assert row[2] == "traveling"

    resp2 = client.post("/me/available")
    assert resp2.status_code == 302
    with engine.connect() as conn:
        row = conn.execute(text("SELECT unavailable_since FROM coachee WHERE id=:c"), {"c": cid}).fetchone()
    assert row[0] is None


def test_unavailable_dashboard_shows_banner(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    _add_coachee_with_overdue_task(client)
    client.get("/logout")

    client.post("/login", data={"username": "unavailsub", "password": "pass123"})
    client.post("/me/unavailable", data={"until": "2099-01-01", "note": "traveling"})
    resp = client.get("/me")
    assert b"unavailable" in resp.data.lower()
    assert b"traveling" in resp.data


def test_overdue_task_is_not_frozen_while_unavailable(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)
    client.get("/logout")

    client.post("/login", data={"username": "unavailsub", "password": "pass123"})
    client.post("/me/unavailable", data={"until": "2099-01-01"})
    client.get("/me")  # would normally trigger _freeze_overdue

    engine = get_engine()
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE coachee_id=:c"), {"c": cid}).scalar()
        strikes = conn.execute(text("SELECT strikes FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert status == "pending"
    assert strikes == 0


def test_overdue_task_is_frozen_normally_once_available(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)
    client.get("/logout")

    client.post("/login", data={"username": "unavailsub", "password": "pass123"})
    client.get("/me")  # not unavailable - should freeze normally

    engine = get_engine()
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE coachee_id=:c"), {"c": cid}).scalar()
    assert status == "missed"


def test_coach_can_declare_and_end_unavailability_on_behalf(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)

    resp = client.post(f"/coach/coachee/{cid}/unavailable", data={"note": "sick"})
    assert resp.status_code == 302
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT unavailable_since FROM coachee WHERE id=:c"), {"c": cid}).fetchone()
    assert row[0] is not None

    resp2 = client.post(f"/coach/coachee/{cid}/available")
    assert resp2.status_code == 302
    with engine.connect() as conn:
        row = conn.execute(text("SELECT unavailable_since FROM coachee WHERE id=:c"), {"c": cid}).fetchone()
    assert row[0] is None


def test_non_owning_coach_cannot_declare_unavailability(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach2", "password": "pass123", "name": "Other Coach 2", "timezone": "UTC"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "othercoach2", "password": "pass123"})

    resp = client.post(f"/coach/coachee/{cid}/unavailable", data={"note": "x"})
    assert resp.status_code == 404


def test_expired_unavailability_no_longer_pauses_freeze(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee_with_overdue_task(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE coachee SET unavailable_since=:since, unavailable_until=:until WHERE id=:c"),
            {"since": "2020-01-01 00:00:00", "until": "2020-01-02", "c": cid},
        )
    client.get("/logout")

    client.post("/login", data={"username": "unavailsub", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE coachee_id=:c"), {"c": cid}).scalar()
    assert status == "missed"
