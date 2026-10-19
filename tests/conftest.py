"""Shared fixtures for DSCoaching tests.

Uses SQLite in-memory for fast, isolated testing.
"""

import os

import pytest

# Set env before any app imports
os.environ["DB_ENGINE"] = "sqlite"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing"
os.environ["ATTACHMENTS_DIR"] = "/tmp/test_attachments"

from app import app as flask_app  # noqa: E402
from database import init_db, reset_engine  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the database engine before each test for full isolation."""
    reset_engine()
    init_db()
    yield
    reset_engine()


@pytest.fixture()
def app():
    """Flask application configured for testing."""
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def coach_session(client):
    """Logged-in coach session (ecb admin)."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    return client


@pytest.fixture()
def coachee_session(coach_session):
    """Create a coachee and return a client logged in as that coachee."""
    # Create coachee as coach
    coach_session.post(
        "/coach/coachee/add",
        data={
            "username": "testcoachee",
            "password": "pass123",
            "name": "Test Coachee",
            "contract": "Follow the rules",
            "safe_word": "RED",
            "task_unveil_time": "06:00",
            "task_freeze_time": "23:00",
            "timezone": "Europe/Brussels",
        },
    )
    coach_session.get("/logout")

    # Login as coachee
    coach_session.post("/login", data={"username": "testcoachee", "password": "pass123"})
    return coach_session
