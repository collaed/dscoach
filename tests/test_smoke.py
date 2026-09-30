"""Smoke tests — verify critical pages load without errors."""


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign In" in resp.data


def test_register_page_loads(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert b"Username" in resp.data


def test_features_page_loads(client):
    resp = client.get("/features")
    assert resp.status_code == 200


def test_setup_redirects_when_coach_exists(client):
    """Setup page redirects to login when a coach already exists (ecb is seeded)."""
    resp = client.get("/setup")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_index_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_static_css_accessible(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert b"--accent" in resp.data


def test_coach_dashboard_requires_auth(client):
    resp = client.get("/coach")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_coachee_dashboard_requires_auth(client):
    resp = client.get("/me")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_dashboard_requires_auth(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_as_coach(client):
    resp = client.post("/login", data={"username": "ecb", "password": "ecbF3T"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/coach" in resp.headers["Location"]


def test_login_invalid_credentials(client):
    resp = client.post("/login", data={"username": "nobody", "password": "wrong"})
    assert resp.status_code == 200
    assert b"Invalid credentials" in resp.data


def test_coach_dashboard_loads_when_authenticated(coach_session):
    resp = coach_session.get("/coach")
    assert resp.status_code == 200
    assert b"Coach Dashboard" in resp.data


def test_logout(coach_session):
    resp = coach_session.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    # After logout, coach dashboard should redirect to login
    resp = coach_session.get("/coach")
    assert resp.status_code == 302
