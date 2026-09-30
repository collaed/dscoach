"""CSRF protection for DSCoaching — stdlib only, no external deps.

Usage:
    1. Register with app: init_csrf(app)
    2. In templates: include {{ csrf_field() }} inside every <form method="post">
    3. Validation is automatic on all POST/PUT/DELETE/PATCH requests.

Exempt routes (e.g., API endpoints) can be decorated with @csrf_exempt.
"""

import hmac
import secrets

from flask import abort, request, session


# Set of view function names exempt from CSRF validation
_exempt_views: set = set()


def csrf_exempt(fn):
    """PURPOSE: Decorator that registers a view function name as exempt from CSRF validation.
    CALLED BY / SCREEN: applied to route handlers that must skip CSRF (e.g. API/webhook endpoints);
    consulted by _validate_csrf(). No screen of its own.
    WHEN: at import time (decoration), on module load / app startup."""
    _exempt_views.add(fn.__name__)
    return fn


def _generate_token() -> str:
    """PURPOSE: Return the per-session CSRF token, creating one if absent.
    CALLED BY / SCREEN: _csrf_field(), _validate_csrf(), and the `csrf_token` context processor
    (init_csrf) — used on every screen that renders a form.
    WHEN: on template render (via csrf_field/csrf_token) and during before_request validation."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _csrf_field() -> str:
    """PURPOSE: Return a hidden HTML input carrying the session CSRF token.
    CALLED BY / SCREEN: exposed to Jinja as `{{ csrf_field() }}` (registered by init_csrf) and
    embedded in every <form method="post"> across all screens.
    WHEN: on template render, whenever a form is emitted."""
    from markupsafe import Markup
    token = _generate_token()
    return Markup(f'<input type="hidden" name="_csrf_token" value="{token}">')


def _validate_csrf():
    """PURPOSE: Validate the CSRF token on state-changing requests (POST/PUT/DELETE/PATCH),
    aborting 403 on mismatch; skips testing mode, exempt views, and the first token-less POST.
    CALLED BY / SCREEN: registered as a before_request hook by init_csrf() — guards every
    form-submitting screen (login, coach, coachee, admin).
    WHEN: before every request, prior to the view function running."""
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return

    # Skip in testing mode
    from flask import current_app
    if current_app.config.get("TESTING"):
        return

    # Skip exempt views
    if request.endpoint:
        view_fn = request.endpoint.rsplit(".", 1)[-1] if "." in request.endpoint else request.endpoint
        if view_fn in _exempt_views:
            return

    # Skip if no session (not logged in, e.g., login form itself still needs token)
    token = session.get("_csrf_token")
    if not token:
        # First POST (login, setup) — generate token and skip validation
        # This allows the first login without a token, then subsequent POSTs are protected
        _generate_token()
        return

    # Check form data or header
    submitted = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token", "")
    if not submitted or not hmac.compare_digest(submitted, token):
        abort(403)


def init_csrf(app):
    """PURPOSE: Wire CSRF protection into the app — register _validate_csrf as before_request and
    expose csrf_field/csrf_token to templates.
    CALLED BY / SCREEN: create_app() in app.py — protects all screens.
    WHEN: once at app-creation / startup."""
    app.before_request(_validate_csrf)
    app.context_processor(lambda: {"csrf_field": _csrf_field, "csrf_token": _generate_token})
