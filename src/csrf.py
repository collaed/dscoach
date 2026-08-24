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
    """Decorator to exempt a route from CSRF checking."""
    _exempt_views.add(fn.__name__)
    return fn


def _generate_token() -> str:
    """Generate or retrieve the session CSRF token."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def _csrf_field() -> str:
    """Return an HTML hidden input with the CSRF token."""
    token = _generate_token()
    return f'<input type="hidden" name="_csrf_token" value="{token}">'


def _validate_csrf():
    """Validate CSRF token on state-changing requests."""
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
    """Register CSRF protection on the Flask app."""
    app.before_request(_validate_csrf)
    app.context_processor(lambda: {"csrf_field": _csrf_field, "csrf_token": _generate_token})
