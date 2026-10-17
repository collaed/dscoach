"""Regression test for H7 (BUG-009): a coachee whose coach row is gone
(delete-mid-session race, or any other way an orphan could arise) must get a
clean login error, not a 500 from `coach_brand.get(...)` on `None`.

Also covers a second bug found while fixing H7: the login route's
fallthrough always overwrote `err` with "Invalid credentials" at the bottom,
silently clobbering the more specific "frozen" / "no longer available"
messages set earlier for a *correct* password.
"""

from database import get_engine
from sqlalchemy import text


def test_login_with_orphaned_coach_does_not_500(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "orphansub",
            "password": "pass123",
            "name": "Orphan Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")

    engine = get_engine()
    with engine.begin() as conn:
        coach_id = conn.execute(text("SELECT coach_id FROM coachee WHERE username='orphansub'")).scalar()
        # Simulate the race directly: coach row vanishes while the coachee row
        # (and its password) still exists, without going through the app's
        # own (now-safe) cascade delete.
        conn.execute(text("DELETE FROM coach WHERE id=:id"), {"id": coach_id})

    resp = client.post("/login", data={"username": "orphansub", "password": "pass123"})
    assert resp.status_code == 200
    assert b"no longer available" in resp.data


def test_login_with_correct_password_on_frozen_coach_shows_frozen_message(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/admin/coach/add",
        data={"username": "freezeme", "password": "pass123", "name": "Freeze Me", "timezone": "UTC"},
    )
    engine = get_engine()
    with engine.connect() as conn:
        coach_id = conn.execute(text("SELECT id FROM coach WHERE username='freezeme'")).scalar()
    client.post(f"/admin/coach/{coach_id}/freeze")
    client.get("/logout")

    resp = client.post("/login", data={"username": "freezeme", "password": "pass123"})
    assert resp.status_code == 200
    assert b"Account frozen" in resp.data
    assert b"Invalid credentials" not in resp.data
