"""Test admin_delete_coach cascade — destructive operation across 12+ tables."""

from database import get_engine
from sqlalchemy import text


def _count_rows(table):
    """Count rows in a table."""
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _setup_coach_with_full_data(client):
    """Create a non-admin coach with a coachee and data in every related table."""
    # Login as admin
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})

    # Create target coach (will be deleted)
    client.post(
        "/admin/coach/add",
        data={"username": "victim", "password": "pass123", "name": "Victim Coach", "timezone": "UTC"},
    )
    client.get("/logout")

    # Login as victim coach, create coachee + data
    client.post("/login", data={"username": "victim", "password": "pass123"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "orphan",
            "password": "pass123",
            "name": "Orphan Coachee",
            "contract": "Test contract",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )

    # Create task template + assignment
    client.post(
        "/coach/tasks",
        data={
            "action": "create",
            "title": "Delete Test Task",
            "description": "Will be cascaded",
            "recurrence": "once",
            "category": "physical",
            "difficulty": "easy",
            "coachee_ids": ["1"],
        },
    )

    # Create conditioning
    client.post(
        "/coach/conditioning",
        data={"target": "all", "prompt_text": "Think about deletion", "prompt_date": "2026-07-01"},
    )

    # Give acknowledgement
    client.post("/coach/ack/1", data={"ack_type": "positive", "description": "Good job", "notes": "Note"})

    # Send note
    client.post("/coach/note/1", data={"content": "A note to delete"})

    client.get("/logout")

    # Login as the coachee and create data in remaining tables
    client.post("/login", data={"username": "orphan", "password": "pass123"})
    client.post("/me/checkin", data={"checkin_type": "morning", "content": "Morning report"})
    client.post("/me/tracking", data={"category": "food", "content": "Ate breakfast"})
    client.post("/me/goal", data={"title": "Survive", "description": "Survive deletion"})
    client.post("/me/journal", data={"content": "Dear diary..."})
    client.get("/logout")

    # Insert remaining data directly (voice_note, progress_photo, contract_history, weekly_summary, profile)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO contract_history (coachee_id, contract_text) VALUES (1, 'Old contract')"))
        conn.execute(text("INSERT INTO psychological_profile (coachee_id, profile_text) VALUES (1, 'A profile')"))
        conn.execute(
            text(
                "INSERT INTO weekly_summary (coachee_id, week_start, summary_text) VALUES (1, '2026-06-24', 'Summary')"
            )
        )


def test_delete_coach_cascades_all_data(client):
    """Deleting a coach removes all coachee data across all 12+ tables, no FK violations."""
    _setup_coach_with_full_data(client)

    # Verify data exists before deletion
    assert _count_rows("coach") == 2  # ecb + victim
    assert _count_rows("coachee") == 1
    assert _count_rows("task_template") >= 1
    assert _count_rows("task_assignment") >= 1
    assert _count_rows("checkin") >= 1
    assert _count_rows("tracking_log") >= 1
    assert _count_rows("note") >= 1
    assert _count_rows("acknowledgement") >= 1
    assert _count_rows("mental_conditioning") >= 1
    assert _count_rows("goal") >= 1
    assert _count_rows("journal") >= 1
    assert _count_rows("contract_history") >= 1
    assert _count_rows("psychological_profile") >= 1
    assert _count_rows("weekly_summary") >= 1

    # Delete the victim coach as admin
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.post("/admin/coach/2/delete", follow_redirects=False)
    assert resp.status_code == 302

    # Verify everything is gone
    assert _count_rows("coach") == 1  # only ecb remains
    assert _count_rows("coachee") == 0
    assert _count_rows("task_assignment") == 0
    assert _count_rows("checkin") == 0
    assert _count_rows("tracking_log") == 0
    assert _count_rows("note") == 0
    assert _count_rows("acknowledgement") == 0
    assert _count_rows("goal") == 0
    assert _count_rows("journal") == 0
    assert _count_rows("contract_history") == 0
    assert _count_rows("psychological_profile") == 0
    assert _count_rows("weekly_summary") == 0
    assert _count_rows("task_template") == 0
    assert _count_rows("mental_conditioning") == 0


def test_cannot_delete_admin_coach(client):
    """Admin coach (ecb) cannot be deleted."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.post("/admin/coach/1/delete", follow_redirects=False)
    assert resp.status_code == 302
    # ecb still exists
    assert _count_rows("coach") == 1


def test_delete_coach_with_no_coachees(client):
    """Deleting a coach with no coachees doesn't error."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/admin/coach/add",
        data={"username": "empty", "password": "pass123", "name": "Empty Coach", "timezone": "UTC"},
    )
    resp = client.post("/admin/coach/2/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert _count_rows("coach") == 1
