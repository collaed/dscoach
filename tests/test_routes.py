"""Integration tests — every route returns expected status codes."""

import json


def _full_setup(client):
    """Create coach + coachee + task + conditioning for route coverage."""
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/coach/coachee/add",
        data={
            "username": "alice",
            "password": "pass123",
            "name": "Alice",
            "contract": "Be good",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "23:59",
            "timezone": "UTC",
        },
    )
    # Create task template + assign
    client.post(
        "/coach/tasks",
        data={
            "action": "create",
            "title": "Morning run",
            "description": "5km run",
            "recurrence": "once",
            "category": "physical",
            "difficulty": "medium",
            "coachee_ids": ["1"],
        },
    )
    # Create conditioning prompt
    client.post(
        "/coach/conditioning",
        data={
            "target": "all",
            "prompt_text": "Reflect on your progress",
            "prompt_date": "2026-07-01",
        },
    )
    # Give acknowledgement
    client.post("/coach/ack/1", data={"ack_type": "positive", "description": "Great start", "notes": ""})
    # Send note
    client.post("/coach/note/1", data={"content": "Keep pushing"})
    client.get("/logout")


# ─── Public Routes ───


class TestPublicRoutes:
    def test_login_get(self, client):
        assert client.get("/login").status_code == 200

    def test_register_get(self, client):
        assert client.get("/register").status_code == 200

    def test_features_get(self, client):
        assert client.get("/features").status_code == 200

    def test_logout(self, client):
        resp = client.get("/logout")
        assert resp.status_code == 302

    def test_index_redirects(self, client):
        resp = client.get("/")
        assert resp.status_code == 302

    def test_register_post_valid(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "newcoach",
                "password": "securepass",
                "name": "New Coach",
                "timezone": "UTC",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_register_post_short_password(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "bad",
                "password": "ab",
                "name": "Bad",
            },
        )
        assert resp.status_code == 200
        assert b"at least 6" in resp.data

    def test_register_post_duplicate_username(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "ecb",
                "password": "anything",
                "name": "Dup",
            },
        )
        assert resp.status_code == 200
        assert b"already taken" in resp.data


# ─── Coach Routes ───


class TestCoachRoutes:
    def test_coach_get_routes(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})

        routes_200 = [
            "/coach",
            "/coach/settings",
            "/coach/branding",
            "/coach/tasks",
            "/coach/grading",
            "/coach/conditioning",
            "/coach/audit",
            "/coach/support",
            "/coach/analyze",
            "/coach/coachee/1",
            "/coach/coachee/1/heatmap",
            "/coach/coachee/1/categories",
            "/coach/coachee/1/summary",
            "/coach/coachee/1/contracts",
        ]
        for path in routes_200:
            resp = client.get(path)
            assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"

    def test_coach_coachee_not_found(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/coach/coachee/999")
        assert resp.status_code == 404

    def test_coach_edit_coachee(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/coachee/1/edit",
            data={
                "contract": "New rules",
                "safe_word": "STOP",
                "task_unveil_time": "07:00",
                "task_freeze_time": "22:00",
                "timezone": "UTC",
                "avatar": "🦊",
                "color_scheme": "#ff0000",
                "telegram_chat_id": "",
                "coachee_features": ["tasks", "checkins"],
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_coach_save_context(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/coachee/1/context", data={"context_text": "Some notes"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coach_profile_prompt(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/coach/coachee/1/profile-prompt")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "prompt" in data

    def test_coach_save_profile(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/coachee/1/profile",
            data=json.dumps({"text": "Alice is disciplined"}),
            content_type="application/json",
        )
        assert resp.status_code == 204

    def test_coach_reset_password(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/coachee/1/reset-password", data={"new_password": "newpass"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coach_task_review(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/task/1/review",
            data={
                "grade": "B",
                "coach_comment": "Good effort",
                "coachee_id": "1",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_coach_template_edit(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/template/1/edit",
            data={
                "title": "Updated",
                "description": "New desc",
                "category": "mental",
                "difficulty": "hard",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_coach_template_delete(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/template/1/delete", follow_redirects=False)
        assert resp.status_code == 302

    def test_coach_pin_note(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/note/1/pin", follow_redirects=False)
        assert resp.status_code == 302

    def test_coach_quick_note(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/quick-note/1", data={"content": "Quick msg"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coach_quick_ack(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/quick-ack/1", data={"ack_type": "positive", "description": "Nice"}, follow_redirects=False
        )
        assert resp.status_code == 302

    def test_coach_goal_review(self, client):
        _full_setup(client)
        # Create a goal as coachee first
        client.post("/login", data={"username": "alice", "password": "pass123"})
        client.post("/me/goal", data={"title": "Run 5k", "description": "Monthly"})
        client.get("/logout")
        # Review as coach
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/goal/1", data={"status": "approved", "coach_notes": "Go for it"}, follow_redirects=False
        )
        assert resp.status_code == 302

    def test_coach_settings_change_features(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/coach/settings",
            data={
                "action": "features",
                "features": ["tasks", "checkins", "tracking"],
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_coach_support_post(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post("/coach/support", data={"message": "Need help"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_library_search(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/coach/library-search")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")


# ─── Coachee Routes ───


class TestCoacheeRoutes:
    def test_coachee_dashboard(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.get("/me")
        assert resp.status_code == 200
        assert b"Alice" in resp.data

    def test_coachee_history(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.get("/me/history")
        assert resp.status_code == 200

    def test_coachee_export(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.get("/me/export")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        data = json.loads(resp.data)
        assert "profile" in data
        assert "checkins" in data

    def test_coachee_checkin(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post(
            "/me/checkin", data={"checkin_type": "morning", "content": "Good morning"}, follow_redirects=False
        )
        assert resp.status_code == 302

    def test_coachee_complete_task(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/task/1", data={"response": "Done it!", "status": "completed"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_tracking(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/tracking", data={"category": "food", "content": "Salad"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_note(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/note", data={"content": "Hi coach"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_goal(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/goal", data={"title": "Meditate daily", "description": ""}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_journal(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/journal", data={"content": "Today was great"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_pause(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        resp = client.post("/me/pause", data={"word": "pause"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_coachee_safe_word_stops(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        client.post("/me/pause", data={"word": "RED"})
        resp = client.get("/me")
        assert b"stopped" in resp.data


# ─── Admin Routes ───


class TestAdminRoutes:
    def test_admin_dashboard(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/admin")
        assert resp.status_code == 200

    def test_admin_add_coach(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.post(
            "/admin/coach/add",
            data={
                "username": "coach2",
                "password": "pass123",
                "name": "Coach 2",
                "timezone": "UTC",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_admin_freeze_coach(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        # Add a non-admin coach first
        client.post(
            "/admin/coach/add",
            data={
                "username": "freezeme",
                "password": "pass123",
                "name": "Freeze Me",
                "timezone": "UTC",
            },
        )
        resp = client.post("/admin/coach/2/freeze", follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_reset_coach_password(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        client.post(
            "/admin/coach/add",
            data={
                "username": "resetme",
                "password": "pass123",
                "name": "Reset Me",
                "timezone": "UTC",
            },
        )
        resp = client.post("/admin/coach/2/reset-password", data={"new_password": "new123"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_support(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/admin/support")
        assert resp.status_code == 200

    def test_admin_delete_coach(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        client.post(
            "/admin/coach/add",
            data={
                "username": "deleteme",
                "password": "pass123",
                "name": "Delete Me",
                "timezone": "UTC",
            },
        )
        resp = client.post("/admin/coach/2/delete", follow_redirects=False)
        assert resp.status_code == 302


# ─── Authorization Checks ───


class TestAuthorization:
    def test_coachee_cannot_access_coach_routes(self, client):
        _full_setup(client)
        client.post("/login", data={"username": "alice", "password": "pass123"})
        coach_routes = ["/coach", "/coach/settings", "/coach/tasks", "/admin"]
        for path in coach_routes:
            resp = client.get(path)
            assert resp.status_code == 302, f"Coachee accessed {path}"
            assert "/login" in resp.headers["Location"]

    def test_coach_cannot_access_coachee_routes(self, client):
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        resp = client.get("/me")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_non_admin_cannot_access_admin(self, client):
        # Register a non-admin coach
        client.post(
            "/register",
            data={
                "username": "regular",
                "password": "pass123",
                "name": "Regular Coach",
            },
        )
        client.post("/login", data={"username": "regular", "password": "pass123"})
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_coach_cannot_see_other_coach_coachee(self, client):
        _full_setup(client)
        # Register second coach
        client.post(
            "/register",
            data={
                "username": "coach2",
                "password": "pass123",
                "name": "Coach 2",
            },
        )
        client.post("/login", data={"username": "coach2", "password": "pass123"})
        # Try to access coachee owned by ecb
        resp = client.get("/coach/coachee/1")
        assert resp.status_code == 404

    def test_frozen_coach_cannot_login(self, client):
        # Create and freeze a coach
        client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
        client.post(
            "/admin/coach/add",
            data={
                "username": "frozen",
                "password": "pass123",
                "name": "Frozen",
                "timezone": "UTC",
            },
        )
        client.post("/admin/coach/2/freeze")
        client.get("/logout")
        # Try to login as frozen — should see "frozen" or "Invalid credentials" (both acceptable)
        resp = client.post("/login", data={"username": "frozen", "password": "pass123"})
        assert resp.status_code == 200
        # Coach should NOT be redirected to dashboard (login fails or shows error)
        assert b"coach" not in resp.headers.get("Location", "").encode() if resp.status_code == 302 else True
        # Should show either "frozen" message or "Invalid credentials"
        assert b"frozen" in resp.data.lower() or b"Invalid" in resp.data
