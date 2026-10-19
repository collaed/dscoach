"""Tests for R26: session idle-timeout, security headers, and Clear-Site-Data on logout."""

import time


def test_idle_session_past_timeout_is_redirected_to_login(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    with client.session_transaction() as sess:
        sess["last_activity"] = time.time() - 31 * 60  # 31 min idle, timeout is 30

    resp = client.get("/coach")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_active_session_within_timeout_stays_logged_in(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    with client.session_transaction() as sess:
        sess["last_activity"] = time.time() - 5 * 60  # 5 min idle, well within 30

    resp = client.get("/coach")
    assert resp.status_code == 200


def test_response_has_hsts_header(client):
    resp = client.get("/login")
    assert "max-age" in resp.headers.get("Strict-Transport-Security", "")


def test_authenticated_response_is_not_cached(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.get("/coach")
    assert resp.headers.get("Cache-Control") == "no-store"


def test_logout_sends_clear_site_data(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.get("/logout")
    assert "cookies" in resp.headers.get("Clear-Site-Data", "")
