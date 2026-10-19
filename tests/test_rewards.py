"""Tests for R24 + R51: reward catalog, redemption, and R49-score-as-currency."""

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="rewardsub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Reward Sub",
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


def _add_reward(client, title="Movie night", cost=10):
    client.post("/coach/rewards", data={"action": "create", "title": title, "point_cost": str(cost)})
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM reward_catalog WHERE title=:t"), {"t": title}).scalar()


def _grant_points(coachee_id, points):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO score_log (coachee_id, points, reason, score_date, note) "
                "VALUES (:c,:p,'manual','2026-01-01','test grant')"
            ),
            {"c": coachee_id, "p": points},
        )


def test_coach_can_create_and_toggle_reward(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    rid = _add_reward(client)
    engine = get_engine()
    with engine.connect() as conn:
        active = conn.execute(text("SELECT active FROM reward_catalog WHERE id=:r"), {"r": rid}).scalar()
    assert active == 1

    client.post("/coach/rewards", data={"action": "toggle", "reward_id": str(rid)})
    with engine.connect() as conn:
        active = conn.execute(text("SELECT active FROM reward_catalog WHERE id=:r"), {"r": rid}).scalar()
    assert active == 0


def test_inactive_reward_hidden_from_coachee_dashboard(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    _add_coachee(client)
    rid = _add_reward(client, title="Hidden reward")
    client.post("/coach/rewards", data={"action": "toggle", "reward_id": str(rid)})
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    resp = client.get("/me")
    assert b"Hidden reward" not in resp.data


def test_redeem_with_sufficient_balance_creates_pending_request_without_deducting(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=10)
    _grant_points(cid, 15)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    resp = client.post(f"/me/reward/{rid}/redeem")
    assert resp.status_code == 302

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, point_cost FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}
        ).fetchone()
        reward_log_rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='reward_redeemed'"), {"c": cid}
        ).fetchall()
    assert row[0] == "pending"
    assert row[1] == 10
    assert len(reward_log_rows) == 0  # nothing spent yet - only approval spends


def test_redeem_with_insufficient_balance_is_rejected(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=100)
    _grant_points(cid, 5)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    client.post(f"/me/reward/{rid}/redeem")

    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}).scalar()
    assert count == 0


def test_coach_approval_spends_the_score_as_currency(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=10)
    _grant_points(cid, 15)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    client.post(f"/me/reward/{rid}/redeem")
    client.get("/logout")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    engine = get_engine()
    with engine.connect() as conn:
        rrid = conn.execute(text("SELECT id FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}).scalar()
    resp = client.post(f"/coach/coachee/{cid}/reward-redemption/{rrid}/approve")
    assert resp.status_code == 302

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM reward_redemption WHERE id=:r"), {"r": rrid}).scalar()
        points = conn.execute(
            text("SELECT points FROM score_log WHERE coachee_id=:c AND reason='reward_redeemed'"), {"c": cid}
        ).scalar()
    assert status == "approved"
    assert points == -10


def test_coach_approval_rejected_if_balance_dropped_since_request(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=10)
    _grant_points(cid, 15)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    client.post(f"/me/reward/{rid}/redeem")
    client.get("/logout")

    # Balance drops below the reward cost before the coach gets to it.
    _grant_points(cid, -10)

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    engine = get_engine()
    with engine.connect() as conn:
        rrid = conn.execute(text("SELECT id FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}).scalar()
    client.post(f"/coach/coachee/{cid}/reward-redemption/{rrid}/approve")

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM reward_redemption WHERE id=:r"), {"r": rrid}).scalar()
        reward_log_rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='reward_redeemed'"), {"c": cid}
        ).fetchall()
    assert status == "pending"
    assert len(reward_log_rows) == 0


def test_coach_can_deny_without_spending_anything(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=10)
    _grant_points(cid, 15)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    client.post(f"/me/reward/{rid}/redeem")
    client.get("/logout")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    engine = get_engine()
    with engine.connect() as conn:
        rrid = conn.execute(text("SELECT id FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}).scalar()
    client.post(f"/coach/coachee/{cid}/reward-redemption/{rrid}/deny")

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM reward_redemption WHERE id=:r"), {"r": rrid}).scalar()
        reward_log_rows = conn.execute(
            text("SELECT 1 FROM score_log WHERE coachee_id=:c AND reason='reward_redeemed'"), {"c": cid}
        ).fetchall()
    assert status == "denied"
    assert len(reward_log_rows) == 0


def test_non_owning_coach_cannot_approve_or_deny(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    rid = _add_reward(client, cost=10)
    _grant_points(cid, 15)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach4", "password": "pass123", "name": "Other Coach 4", "timezone": "UTC"},
    )
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    client.post(f"/me/reward/{rid}/redeem")
    client.get("/logout")

    engine = get_engine()
    with engine.connect() as conn:
        rrid = conn.execute(text("SELECT id FROM reward_redemption WHERE coachee_id=:c"), {"c": cid}).scalar()

    client.post("/login", data={"username": "othercoach4", "password": "pass123"})
    resp = client.post(f"/coach/coachee/{cid}/reward-redemption/{rrid}/approve")
    assert resp.status_code == 404
    resp2 = client.post(f"/coach/coachee/{cid}/reward-redemption/{rrid}/deny")
    assert resp2.status_code == 404


def test_coachee_cannot_redeem_another_coachs_reward(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    _grant_points(cid, 100)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach5", "password": "pass123", "name": "Other Coach 5", "timezone": "UTC"},
    )
    client.get("/logout")

    client.post("/login", data={"username": "othercoach5", "password": "pass123"})
    other_rid = _add_reward(client, title="Other coach's reward", cost=10)
    client.get("/logout")

    client.post("/login", data={"username": "rewardsub", "password": "pass123"})
    resp = client.post(f"/me/reward/{other_rid}/redeem")
    assert resp.status_code == 404
