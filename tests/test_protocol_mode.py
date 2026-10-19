"""Tests for R42: protocol mode toggle (formal/relaxed)."""

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="protosub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Proto Sub",
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


def test_default_protocol_mode_is_relaxed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT protocol_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
    assert mode == "relaxed"


def test_coach_can_set_formal_mode_and_it_is_logged(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)

    resp = client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "formal"})
    assert resp.status_code == 302

    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT protocol_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
        log_rows = conn.execute(
            text("SELECT mode, changed_by_coach_id FROM protocol_mode_log WHERE coachee_id=:c"), {"c": cid}
        ).fetchall()
    assert mode == "formal"
    assert len(log_rows) == 1
    assert log_rows[0][0] == "formal"


def test_coach_can_switch_back_to_relaxed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "formal"})
    client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "relaxed"})

    engine = get_engine()
    with engine.connect() as conn:
        mode = conn.execute(text("SELECT protocol_mode FROM coachee WHERE id=:c"), {"c": cid}).scalar()
        count = conn.execute(text("SELECT COUNT(*) FROM protocol_mode_log WHERE coachee_id=:c"), {"c": cid}).scalar()
    assert mode == "relaxed"
    assert count == 2


def test_non_owning_coach_cannot_set_protocol_mode(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach", "password": "pass123", "name": "Other Coach", "timezone": "UTC"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "othercoach", "password": "pass123"})

    resp = client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "formal"})
    assert resp.status_code == 404


def test_coachee_dashboard_shows_formal_badge_when_formal(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "formal"})
    client.get("/logout")

    client.post("/login", data={"username": "protosub", "password": "pass123"})
    resp = client.get("/me")
    assert b"Formal" in resp.data


def test_coachee_dashboard_hides_formal_badge_when_relaxed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    _add_coachee(client)
    client.get("/logout")

    client.post("/login", data={"username": "protosub", "password": "pass123"})
    resp = client.get("/me")
    assert b"Formal" not in resp.data


def test_note_submitted_in_formal_mode_is_tagged(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(f"/coach/coachee/{cid}/protocol-mode", data={"mode": "formal"})
    client.get("/logout")

    client.post("/login", data={"username": "protosub", "password": "pass123"})
    client.post("/me/note", data={"content": "a formal note"})

    engine = get_engine()
    with engine.connect() as conn:
        tagged = conn.execute(
            text("SELECT tagged_mode FROM note WHERE coachee_id=:c AND content='a formal note'"), {"c": cid}
        ).scalar()
    assert tagged == "formal"


def test_note_submitted_in_relaxed_mode_is_tagged_relaxed(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.get("/logout")

    client.post("/login", data={"username": "protosub", "password": "pass123"})
    client.post("/me/note", data={"content": "a relaxed note"})

    engine = get_engine()
    with engine.connect() as conn:
        tagged = conn.execute(
            text("SELECT tagged_mode FROM note WHERE coachee_id=:c AND content='a relaxed note'"), {"c": cid}
        ).scalar()
    assert tagged == "relaxed"
