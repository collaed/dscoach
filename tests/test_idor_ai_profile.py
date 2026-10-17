"""Regression test for BUG-020: the AI-profile routes must verify the coachee
belongs to the logged-in coach, same as every other per-coachee route.
"""


def _setup_two_coaches_and_coachee(client):
    """Admin creates coachA + coachB; coachA creates a coachee. Returns the coachee id."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/admin/coach/add",
        data={"username": "coachA", "password": "pass123", "name": "Coach A", "timezone": "UTC"},
    )
    client.post(
        "/admin/coach/add",
        data={"username": "coachB", "password": "pass123", "name": "Coach B", "timezone": "UTC"},
    )
    client.get("/logout")

    client.post("/login", data={"username": "coachA", "password": "pass123"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "idorsub",
            "password": "pass123",
            "name": "IDOR Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM coachee WHERE username='idorsub'")).scalar()


def test_cannot_fetch_profile_prompt_for_another_coachs_coachee(client):
    cid = _setup_two_coaches_and_coachee(client)
    client.post("/login", data={"username": "coachB", "password": "pass123"})
    resp = client.get(f"/coach/coachee/{cid}/profile-prompt")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Coachee not found"


def test_cannot_generate_profile_for_another_coachs_coachee(client):
    cid = _setup_two_coaches_and_coachee(client)
    client.post("/login", data={"username": "coachB", "password": "pass123"})
    resp = client.post(f"/coach/coachee/{cid}/generate-profile")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Coachee not found"


def test_cannot_save_profile_text_for_another_coachs_coachee(client):
    cid = _setup_two_coaches_and_coachee(client)
    client.post("/login", data={"username": "coachB", "password": "pass123"})
    resp = client.post(f"/coach/coachee/{cid}/profile", json={"text": "injected by coach B"})
    assert resp.status_code == 404

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT profile_text FROM psychological_profile WHERE coachee_id=:cid"), {"cid": cid}
        ).fetchone()
    assert row is None  # nothing was written


def test_owning_coach_can_still_use_all_three_routes(client):
    """Make sure the fix didn't break the legitimate, same-coach case."""
    cid = _setup_two_coaches_and_coachee(client)
    client.post("/login", data={"username": "coachA", "password": "pass123"})

    assert client.get(f"/coach/coachee/{cid}/profile-prompt").status_code == 200
    assert client.post(f"/coach/coachee/{cid}/profile", json={"text": "legit note"}).status_code == 204

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT profile_text FROM psychological_profile WHERE coachee_id=:cid"), {"cid": cid}
        ).fetchone()
    assert row is not None
    assert row[0] == "legit note"
