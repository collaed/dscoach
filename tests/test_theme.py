"""Tests for R50 - FetLife-inspired noir theme (devdocs/plan-aesthetic-noir.md)."""

import os


def _setup_coachee(client, username="themetest"):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Theme Tester",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    client.get("/logout")


def test_default_theme_is_default_for_a_fresh_coach(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    html = client.get("/coach/settings").data.decode()
    assert 'class="font-clean theme-default"' in html


def test_toggling_theme_updates_body_class_and_persists(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.get("/theme/noir")
    html = client.get("/coach/settings").data.decode()
    assert "theme-noir" in html

    from database import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        pref = conn.execute(text("SELECT theme_pref FROM coach WHERE username='ecb'")).scalar()
    assert pref == "noir"


def test_theme_preference_survives_a_fresh_login(client):
    """Setting it, logging out, and logging back in should restore it from the DB row,
    not reset to default (same pattern as font_pref)."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.get("/theme/noir")
    client.get("/logout")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    html = client.get("/coach/settings").data.decode()
    assert "theme-noir" in html


def test_invalid_theme_value_is_ignored(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.get("/theme/noir")
    client.get("/theme/not-a-real-theme")  # should be rejected, not applied
    html = client.get("/coach/settings").data.decode()
    assert "theme-noir" in html  # unchanged


def test_coachee_can_set_their_own_theme_independently(client):
    _setup_coachee(client)
    client.post("/login", data={"username": "themetest", "password": "pass123"})
    client.get("/theme/noir")
    html = client.get("/me").data.decode()
    assert "theme-noir" in html

    # Coach's own preference is untouched.
    client.get("/logout")
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    coach_html = client.get("/coach/settings").data.decode()
    assert "theme-default" in coach_html


def test_noir_theme_toggle_rendered_on_both_settings_screens(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    assert "/theme/noir" in client.get("/coach/settings").data.decode()

    _setup_coachee(client)
    client.post("/login", data={"username": "themetest", "password": "pass123"})
    assert "/theme/noir" in client.get("/me").data.decode()


def test_noir_branding_preset_button_present(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    html = client.get("/coach/branding").data.decode()
    assert "applyNoirPreset" in html
    assert "#b3153a" in html


def test_noir_css_tokens_present_in_stylesheet():
    """Static guard: the documented token values actually ship in the CSS, not just the plan."""
    css_path = os.path.join(os.path.dirname(__file__), "..", "static", "style.css")
    with open(css_path) as f:
        css = f.read()
    assert "body.theme-noir" in css
    for token in ("#1a1a1a", "#d8d8d8", "#a9a9a9", "#b3153a"):
        assert token in css
