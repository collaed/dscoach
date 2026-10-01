"""Unit tests for feature flag system (_features_for logic)."""

import json


def _set_coach_features(features_dict):
    """Set feature flags for coach id=1."""
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET features=:f WHERE id=1"), {"f": json.dumps(features_dict)})


def _set_coachee_features(features_dict):
    """Set feature flags override for coachee id=1."""
    from sqlalchemy import text

    from database import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET features=:f WHERE id=1"), {"f": json.dumps(features_dict)})


def _setup_coachee(client):
    """Create a coachee."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "feattest",
            "password": "pass123",
            "name": "Feature Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "06:00",
            "task_freeze_time": "23:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")


def test_coach_enables_all_by_default(client):
    """No features JSON on coach → all features enabled."""
    _setup_coachee(client)

    # Login as coachee and check dashboard renders all tabs
    client.post("/login", data={"username": "feattest", "password": "pass123"})
    resp = client.get("/me")
    html = resp.data.decode()

    # All feature tabs should be present
    assert "Tasks" in html
    assert "Morning" in html or "Evening" in html  # checkins
    assert "Tracking" in html
    assert "Mind" in html  # conditioning
    assert "Notes" in html
    assert "Goals" in html
    assert "Journal" in html
    assert "Photos" in html


def test_coach_disables_feature(client):
    """Coach disables goals → coachee dashboard doesn't show goals tab."""
    _setup_coachee(client)

    # Coach disables goals
    _set_coach_features(
        {
            "tasks": True,
            "checkins": True,
            "tracking": True,
            "conditioning": True,
            "notes": True,
            "goals": False,
            "journal": True,
            "photos": True,
            "ai_profile": True,
            "telegram": True,
        }
    )

    client.post("/login", data={"username": "feattest", "password": "pass123"})
    resp = client.get("/me")
    html = resp.data.decode()

    # Goals tab should NOT appear
    assert 'data-tab="goals"' not in html
    # But other tabs should still be there
    assert "Tasks" in html


def test_coachee_can_disable_what_coach_enabled(client):
    """Coach enables journal, coachee disables it → journal tab hidden."""
    _setup_coachee(client)

    _set_coach_features(
        {
            "tasks": True,
            "checkins": True,
            "tracking": True,
            "conditioning": True,
            "notes": True,
            "goals": True,
            "journal": True,
            "photos": True,
            "ai_profile": True,
            "telegram": True,
        }
    )
    _set_coachee_features({"journal": False})

    client.post("/login", data={"username": "feattest", "password": "pass123"})
    resp = client.get("/me")
    html = resp.data.decode()

    assert 'data-tab="journal"' not in html
    assert "Goals" in html  # others still visible


def test_coachee_cannot_enable_what_coach_disabled(client):
    """Coach disables photos, coachee tries to enable → still disabled."""
    _setup_coachee(client)

    _set_coach_features(
        {
            "tasks": True,
            "checkins": True,
            "tracking": True,
            "conditioning": True,
            "notes": True,
            "goals": True,
            "journal": True,
            "photos": False,
            "ai_profile": True,
            "telegram": True,
        }
    )
    _set_coachee_features({"photos": True})  # coachee tries to enable

    client.post("/login", data={"username": "feattest", "password": "pass123"})
    resp = client.get("/me")
    html = resp.data.decode()

    assert 'data-tab="photos"' not in html
