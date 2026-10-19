"""Regression tests for H5 (BUG-010): oversized form input must be rejected
with a clean validation error before it reaches a length-bounded DB column,
not surface as a Postgres DataError (500).
"""


def test_register_rejects_oversized_username(client):
    resp = client.post(
        "/register",
        data={"username": "x" * 101, "name": "Someone", "password": "pass123", "timezone": "UTC"},
    )
    assert resp.status_code == 200
    assert b"must be at most 100 characters" in resp.data


def test_register_rejects_oversized_name(client):
    resp = client.post(
        "/register",
        data={"username": "shortname", "name": "y" * 201, "password": "pass123", "timezone": "UTC"},
    )
    assert resp.status_code == 200
    assert b"must be at most 200 characters" in resp.data


def test_register_accepts_normal_length_input(client):
    resp = client.post(
        "/register",
        data={"username": "normaluser", "name": "Normal Name", "password": "pass123", "timezone": "UTC"},
    )
    assert resp.status_code == 302


def test_add_coachee_rejects_oversized_username(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.post(
        "/coach/coachee/add",
        data={
            "username": "z" * 101,
            "password": "pass123",
            "name": "Someone",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 302  # redirects back to the form, not an insert attempt
    resp2 = client.get(resp.headers["Location"])
    assert b"must be at most 100 characters" in resp2.data


def test_add_coachee_accepts_normal_length_input(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.post(
        "/coach/coachee/add",
        data={
            "username": "normalcoachee",
            "password": "pass123",
            "name": "Normal Coachee",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "08:00",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/coach")
