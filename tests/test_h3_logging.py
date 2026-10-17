"""Tests for H3 (BUG-005/BUG-015): failures that must stay non-blocking should
still be printed, not silently swallowed.
"""

from unittest.mock import MagicMock, patch


def test_audit_failure_is_printed_not_swallowed(client, capsys):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})

    with client.application.app_context():
        from helpers import _audit

        with patch("helpers.db", side_effect=RuntimeError("db unavailable")):
            _audit("test_action")  # must not raise

    captured = capsys.readouterr()
    assert "[_audit]" in captured.out
    assert "db unavailable" in captured.out


def test_mood_sparkline_failure_is_printed_and_returns_empty(client, capsys):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})

    with client.application.app_context():
        from automation import _mood_sparkline

        broken_cursor = MagicMock()
        broken_cursor.execute.side_effect = RuntimeError("query exploded")
        with patch("automation.db", return_value=broken_cursor):
            result = _mood_sparkline(1)

    assert result == []
    captured = capsys.readouterr()
    assert "[_mood_sparkline]" in captured.out
    assert "query exploded" in captured.out


def test_photo_validation_failure_is_printed_not_swallowed(client, capsys):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "pvtest",
            "password": "pass123",
            "name": "PV Tester",
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
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_template (coach_id, title, description, recurrence, category, is_reserve) "
                "VALUES (1, 'PV Task', '', 'once', 'mental', 1)"
            )
        )
        tmpl_id = conn.execute(text("SELECT MAX(id) FROM task_template")).scalar()

    client.post("/login", data={"username": "pvtest", "password": "pass123"})
    client.get("/me")  # auto-assigns the reserve task

    with engine.connect() as conn:
        tid = conn.execute(
            text("SELECT id FROM task_assignment WHERE coachee_id=1 AND template_id=:t"), {"t": tmpl_id}
        ).scalar()

    tiny_png = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    with (
        patch("photo_validation.should_validate_photo", return_value=True),
        patch("photo_validation.validate_photo_proof", side_effect=RuntimeError("AI backend down")),
    ):
        resp = client.post(f"/me/task/{tid}", data={"response": "done", "attachment_data": tiny_png})

    assert resp.status_code == 302  # submission still succeeds despite the validation failure
    captured = capsys.readouterr()
    assert "[complete_task]" in captured.out
    assert "AI backend down" in captured.out
