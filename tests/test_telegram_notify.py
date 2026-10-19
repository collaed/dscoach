"""Regression test for BUG-019: the Telegram bot token must never reach the
browser. Covers the /coach/coachee/<cid>/telegram-notify proxy route that
replaced the old client-side fetch() directly to api.telegram.org.
"""

from unittest.mock import MagicMock, patch

from database import get_engine
from sqlalchemy import text


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
            "username": "sub1",
            "password": "pass123",
            "name": "Sub One",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")

    engine = get_engine()
    with engine.connect() as conn:
        cid = conn.execute(text("SELECT id FROM coachee WHERE username='sub1'")).scalar()
    return cid


def test_requires_login(client):
    """Unauthenticated POST is redirected to login, not processed."""
    resp = client.post("/coach/coachee/1/telegram-notify", json={"message": "hi"})
    assert resp.status_code in (302, 401, 403)


def test_cannot_notify_another_coachs_coachee(client):
    """Coach B must not be able to trigger a notification for Coach A's coachee (IDOR guard)."""
    cid = _setup_two_coaches_and_coachee(client)

    client.post("/login", data={"username": "coachB", "password": "pass123"})
    resp = client.post(f"/coach/coachee/{cid}/telegram-notify", json={"message": "hi"})
    assert resp.status_code == 404


def test_returns_sent_false_when_not_configured(client):
    """No bot token / chat id configured -> no-op, matching the old client-side early-return."""
    cid = _setup_two_coaches_and_coachee(client)

    client.post("/login", data={"username": "coachA", "password": "pass123"})
    resp = client.post(f"/coach/coachee/{cid}/telegram-notify", json={"message": "hi"})
    assert resp.status_code == 200
    assert resp.get_json() == {"sent": False}


def test_sends_server_side_and_never_leaks_token_to_the_page(client):
    """With a bot token configured, the send happens server-side; the token never appears
    in the coachee detail page HTML (the actual regression this test guards against)."""
    cid = _setup_two_coaches_and_coachee(client)

    secret_token = "123456:AAFakeSecretTelegramBotTokenValue"
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coach SET telegram_bot_token=:t WHERE username='coachA'"), {"t": secret_token})
        conn.execute(text("UPDATE coachee SET telegram_chat_id=:c WHERE id=:id"), {"c": "999", "id": cid})

    client.post("/login", data={"username": "coachA", "password": "pass123"})

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=b"{}")
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        resp = client.post(f"/coach/coachee/{cid}/telegram-notify", json={"message": "Task graded: A"})
    assert resp.status_code == 200
    assert resp.get_json() == {"sent": True}
    # The server made exactly one outbound call, and it carried the token - proving the
    # send happens here, not in the browser.
    assert mock_urlopen.call_count == 1
    sent_url = mock_urlopen.call_args[0][0].full_url
    assert secret_token in sent_url

    # The coachee detail page itself must never embed the token anywhere in its HTML/JS.
    page = client.get(f"/coach/coachee/{cid}")
    assert secret_token not in page.data.decode()


def test_llm_key_never_rendered_on_coachee_detail_or_analyze_pages(client):
    """Regression guard for the other half of BUG-019: the dead `llm_key`/LKEY client-side
    exposure (Mistral key) must be gone from both pages that used to render it."""
    cid = _setup_two_coaches_and_coachee(client)
    client.post("/login", data={"username": "coachA", "password": "pass123"})

    detail_html = client.get(f"/coach/coachee/{cid}").data.decode()
    assert "LKEY" not in detail_html
    assert "llm_key" not in detail_html

    analyze_html = client.get("/coach/analyze").data.decode()
    assert "llm_key" not in analyze_html
