"""Tests for R48 - probabilistic proof demand (devdocs/plan-proof-and-scoring.md)."""


def _count_task_assignments(coachee_id):
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM task_assignment WHERE coachee_id=:cid"), {"cid": coachee_id}
        ).scalar()


def _proof_required_for_latest_assignment(coachee_id):
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT proof_required FROM task_assignment WHERE coachee_id=:cid ORDER BY id DESC LIMIT 1"),
            {"cid": coachee_id},
        ).scalar()


def _create_template(coach_id=1, is_reserve=0, recur_days=None, proof_pct=0, title="Proof Test Task"):
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, "
                "is_reserve, recur_days, proof_pct) "
                "VALUES (:cid, :title, '', 'once', 'mental', :reserve, :rd, :pct)"
            ),
            {"cid": coach_id, "title": title, "reserve": is_reserve, "rd": recur_days, "pct": proof_pct},
        )
        return conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()


def _setup_coachee(client, username="prooftest"):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Proof Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    client.get("/logout")


# --- Pure function (REQ-48.1, REQ-48.7, REQ-48.11) ---


def test_proof_pct_zero_is_never_required():
    from tasks import _roll_proof_required

    assert all(_roll_proof_required(0) == 0 for _ in range(50))
    assert _roll_proof_required(None) == 0  # REQ-48.7: unset behaves as 0


def test_proof_pct_hundred_is_always_required():
    from tasks import _roll_proof_required

    assert all(_roll_proof_required(100) == 1 for _ in range(50))


def test_proof_pct_fifty_is_a_seeded_deterministic_mix():
    """Local Random instance (REQ-48.11): seeding it makes the roll deterministic
    and the test order-independent (doesn't touch global `random` state)."""
    import tasks

    tasks._proof_rng.seed(12345)
    rolls = [tasks._roll_proof_required(50) for _ in range(30)]
    assert 0 in rolls and 1 in rolls  # both outcomes occur
    # re-seeding reproduces the exact same sequence
    tasks._proof_rng.seed(12345)
    rolls_again = [tasks._roll_proof_required(50) for _ in range(30)]
    assert rolls == rolls_again


# --- Wired into every assignment path (REQ-48.6) ---


def test_rolled_on_reserve_assignment_path(client):
    """_auto_assign_reserves's reserve fallback (one of the 5 real INSERT sites)."""
    _setup_coachee(client)
    _create_template(is_reserve=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")  # triggers _auto_assign_reserves

    assert _count_task_assignments(1) == 1
    assert _proof_required_for_latest_assignment(1) == 1


def test_rolled_on_recurring_assignment_path(client):
    """_auto_assign_reserves's recurring first-time-assignment branch."""
    _setup_coachee(client)
    _create_template(recur_days=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")

    assert _proof_required_for_latest_assignment(1) == 1


def test_rolled_on_manual_create_and_assign_path(client):
    """routes_coach.py's manage_tasks 'create new template + assign' handler."""
    _setup_coachee(client)

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/tasks",
        data={
            "action": "create",
            "title": "Manual Proof Task",
            "description": "",
            "recurrence": "once",
            "category": "mental",
            "difficulty": "medium",
            "proof_pct": "100",
            "coachee_ids": ["1"],
        },
    )

    assert _proof_required_for_latest_assignment(1) == 1


def test_rolled_on_assign_from_library_path(client):
    """routes_coach.py's 'assign_library' action (assigning an existing template)."""
    _setup_coachee(client)
    tmpl_id = _create_template(proof_pct=100, title="Library Task")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/tasks",
        data={"action": "assign_library", "template_id": str(tmpl_id), "coachee_ids": ["1"]},
    )

    assert _proof_required_for_latest_assignment(1) == 1


def test_rolled_on_onboarding_path(client):
    """tasks.py::_run_onboarding, triggered via /me on a coachee's first day."""
    _setup_coachee(client)
    tmpl_id = _create_template(proof_pct=100, title="Onboarding Task")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO onboarding_step (coach_id, day_offset, template_id) VALUES (1, 0, :tid)"),
            {"tid": tmpl_id},
        )

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")

    assert _proof_required_for_latest_assignment(1) == 1


def test_rolled_on_auto_rule_assign_task_path(client):
    """automation.py::_run_auto_rules' assign_task action branch."""
    _setup_coachee(client)
    tmpl_id = _create_template(proof_pct=100, title="Auto-rule Task")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auto_rule (coach_id, name, trigger, action_type, action_template, active) "
                "VALUES (1, 'test rule', 'checkin_submitted', 'assign_task', :tid, 1)"
            ),
            {"tid": str(tmpl_id)},
        )

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.post("/me/checkin", data={"checkin_type": "morning", "content": "hi"})

    assert _proof_required_for_latest_assignment(1) == 1


# --- Persistence & stability (REQ-48.3, REQ-48.10) ---


def test_decision_persisted_and_stable_across_reloads(client):
    """Reloading /me must not re-roll proof_required on an existing assignment."""
    _setup_coachee(client)
    _create_template(is_reserve=1, proof_pct=50)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")
    first = _proof_required_for_latest_assignment(1)
    client.get("/me")
    client.get("/me")
    assert _proof_required_for_latest_assignment(1) == first


def test_editing_template_proof_pct_does_not_change_pending_assignment(client):
    """REQ-48.10: editing proof_pct after the fact must not retroactively flip
    an already-persisted proof_required on a pending assignment."""
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")
    assert _proof_required_for_latest_assignment(1) == 1

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE task_template SET proof_pct=0 WHERE id=:tid"), {"tid": tmpl_id})

    # The already-persisted assignment keeps its original roll.
    assert _proof_required_for_latest_assignment(1) == 1


# --- Completion enforcement (REQ-48.5) ---


def test_complete_without_photo_rejected_when_proof_required(client):
    _setup_coachee(client)
    _create_template(is_reserve=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(text("SELECT id FROM task_assignment WHERE coachee_id=1")).scalar()

    resp = client.post(f"/me/task/{tid}", data={"response": "done, no photo"}, follow_redirects=True)
    assert b"requires a photo" in resp.data

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE id=:tid"), {"tid": tid}).scalar()
    assert status == "pending"


def test_complete_with_photo_accepted_when_proof_required(client):
    _setup_coachee(client)
    _create_template(is_reserve=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(text("SELECT id FROM task_assignment WHERE coachee_id=1")).scalar()

    tiny_png = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    client.post(f"/me/task/{tid}", data={"response": "done", "attachment_data": tiny_png})

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE id=:tid"), {"tid": tid}).scalar()
    assert status == "completed"


def test_partial_submission_allowed_without_photo_even_when_required(client):
    """A partial submission (not claiming completion) is not blocked by proof_required."""
    _setup_coachee(client)
    _create_template(is_reserve=1, proof_pct=100)

    client.post("/login", data={"username": "prooftest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(text("SELECT id FROM task_assignment WHERE coachee_id=1")).scalar()

    client.post(f"/me/task/{tid}", data={"response": "not done yet", "status": "partial"})

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE id=:tid"), {"tid": tid}).scalar()
    assert status == "partial"
