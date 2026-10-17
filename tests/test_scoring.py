"""Tests for R49 - points & persisted daily score (devdocs/plan-proof-and-scoring.md)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def _score_log_rows(coachee_id=1):
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        return [
            dict(row._mapping)
            for row in conn.execute(
                text("SELECT * FROM score_log WHERE coachee_id=:cid ORDER BY id"), {"cid": coachee_id}
            )
        ]


def _create_template(coach_id=1, is_reserve=0, points=0, proof_pct=0, title="Scoring Test Task"):
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, "
                "is_reserve, points, proof_pct) "
                "VALUES (:cid, :title, '', 'once', 'mental', :reserve, :pts, :pct)"
            ),
            {"cid": coach_id, "title": title, "reserve": is_reserve, "pts": points, "pct": proof_pct},
        )
        return conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()


def _setup_coachee(client, username="scoretest"):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Score Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    client.get("/logout")


# --- Pure functions (REQ-49.5, REQ-49.7) ---


def test_week_key_monday_first():
    from scoring import week_key

    # 2026-10-21 is a Wednesday
    d = date(2026, 10, 21)
    assert week_key(d, "mon") == date(2026, 10, 19)  # the Monday of that week
    assert week_key(d, "sun") == date(2026, 10, 18)  # the Sunday of that week


def test_rollup_groups_by_month():
    from scoring import rollup

    daily = {date(2026, 3, 5): 10, date(2026, 3, 20): 5, date(2026, 4, 1): 7}
    months = rollup(daily, "month")
    assert months[date(2026, 3, 1)] == 15
    assert months[date(2026, 4, 1)] == 7


def test_coachee_local_date_honors_timezone(client):
    """REQ-49.4: score_date must use the coachee's own timezone, not naive UTC."""
    _setup_coachee(client)
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET timezone='Pacific/Kiritimati' WHERE id=1"))  # UTC+14

    from scoring import _coachee_local_date

    expected = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()
    with client.application.app_context():
        assert _coachee_local_date(1) == expected


# --- award_points idempotency (REQ-49.9) ---


def test_award_points_is_idempotent_per_assignment_and_reason(client):
    from scoring import award_points

    with client.application.app_context():
        award_points(1, 5, "task_completed", task_assignment_id=42)
        award_points(1, 5, "task_completed", task_assignment_id=42)  # re-submit
    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == 42]
    assert len(rows) == 1


def test_award_points_zero_is_a_noop(client):
    from scoring import award_points

    before = len(_score_log_rows(1))
    with client.application.app_context():
        award_points(1, 0, "task_completed", task_assignment_id=99)
    assert len(_score_log_rows(1)) == before


def test_null_task_assignment_id_awards_can_coexist(client):
    """REQ-49.9: manual/checkin awards (task_assignment_id=NULL) must not collide with
    each other under the unique constraint - standard SQL NULL semantics."""
    from scoring import award_points

    with client.application.app_context():
        award_points(1, 3, "manual", note="first")
        award_points(1, 4, "manual", note="second")
    manual_rows = [r for r in _score_log_rows(1) if r["reason"] == "manual"]
    assert len(manual_rows) == 2


# --- Completion / miss hooks, end to end (REQ-49.2) ---


def test_completing_a_task_awards_its_points(client):
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, points=5)

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()

    client.post(f"/me/task/{tid}", data={"response": "done"})

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    assert any(r["reason"] == "task_completed" and r["points"] == 5 for r in rows)


def test_missing_a_task_awards_negative_penalty(client):
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, points=5)

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()
    with engine.begin() as conn:
        # force it overdue
        conn.execute(text("UPDATE task_assignment SET frozen_after='2000-01-01 00:00:00' WHERE id=:tid"), {"tid": tid})

    client.get("/me")  # triggers _freeze_overdue

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    assert any(r["reason"] == "task_missed" and r["points"] == -5 for r in rows)


def test_proof_bonus_awarded_only_with_required_proof_and_photo(client):
    """REQ-49.10: the bonus applies only when proof was required AND a photo was attached."""
    _setup_coachee(client)
    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET features=:f WHERE id=1"), {"f": '{"proof_bonus": 2}'})

    tmpl_id = _create_template(is_reserve=1, points=5, proof_pct=100)

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()

    tiny_png = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    client.post(f"/me/task/{tid}", data={"response": "done", "attachment_data": tiny_png})

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    assert any(r["reason"] == "proof_bonus" and r["points"] == 2 for r in rows)


def test_no_proof_bonus_without_required_proof(client):
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, points=5, proof_pct=0)  # proof never required

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()

    client.post(f"/me/task/{tid}", data={"response": "done"})

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    assert not any(r["reason"] == "proof_bonus" for r in rows)


# --- REQ-49.2b: excused-miss reversal ---


def test_excusing_a_missed_task_reverses_the_penalty(client):
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, points=5)

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()
    with engine.begin() as conn:
        conn.execute(text("UPDATE task_assignment SET frozen_after='2000-01-01 00:00:00' WHERE id=:tid"), {"tid": tid})
    client.get("/me")  # -> missed, -5 points

    client.get("/logout")
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(f"/coach/task/{tid}/excuse", data={"coachee_id": "1"})

    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM task_assignment WHERE id=:tid"), {"tid": tid}).scalar()
    assert status == "excused"

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    total = sum(r["points"] for r in rows)
    assert total == 0  # -5 (missed) + 5 (miss_reversed) nets to zero
    assert any(r["reason"] == "miss_reversed" for r in rows)


def test_excusing_twice_does_not_double_reverse(client):
    _setup_coachee(client)
    tmpl_id = _create_template(is_reserve=1, points=5)

    client.post("/login", data={"username": "scoretest", "password": "pass123"})
    client.get("/me")

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()
    with engine.begin() as conn:
        conn.execute(text("UPDATE task_assignment SET frozen_after='2000-01-01 00:00:00' WHERE id=:tid"), {"tid": tid})
    client.get("/me")

    client.get("/logout")
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(f"/coach/task/{tid}/excuse", data={"coachee_id": "1"})
    client.post(f"/coach/task/{tid}/excuse", data={"coachee_id": "1"})  # second attempt: already excused

    rows = [r for r in _score_log_rows(1) if r["task_assignment_id"] == tid]
    assert sum(1 for r in rows if r["reason"] == "miss_reversed") == 1


# --- BUG-021: features-JSON merge, not replace ---


def test_editing_coachee_settings_preserves_week_start_preference(client):
    """Saving the main coachee-edit form must not wipe out week_start (or any other
    key in coachee.features the form doesn't itself manage)."""
    _setup_coachee(client)

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post("/coach/coachee/1/week-start", data={"week_start": "sun"})
    client.post(
        "/coach/coachee/1/edit",
        data={
            "contract": "updated contract",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
            "avatar": "x",
            "color_scheme": "#e94560",
        },
    )

    from scoring import get_week_start_pref

    with client.application.app_context():
        assert get_week_start_pref(1, 1) == "sun"
