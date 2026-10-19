"""Tests for H4 (BUG-007): the login page's forgot-password mailto must not
hardcode a developer's personal address — it's opt-in via SUPPORT_EMAIL.
"""


def test_forgot_password_link_hidden_when_support_email_unset(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Forgot password" not in resp.data
    assert b"papillon.severin" not in resp.data


def test_forgot_password_link_uses_configured_support_email(client, monkeypatch):
    monkeypatch.setattr("helpers.SUPPORT_EMAIL", "ops@example.com")
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Forgot password" in resp.data
    assert b"mailto:ops@example.com" in resp.data
    assert b"papillon.severin" not in resp.data
