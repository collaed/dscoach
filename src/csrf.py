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
    """Decorator to exempt a route from CSRF checking.

    Called by: nothing currently uses this decorator — every existing route
    goes through normal validation. Exists for a future API/webhook endpoint
    that can't carry a session-bound token (e.g. a Telegram webhook).
    """
    _exempt_views.add(fn.__name__)
    return fn


def _generate_token() -> str:
    """Generate or retrieve the session CSRF token.

    Called by: _csrf_field() below, and exposed to every template directly
    as `csrf_token()` via the context processor registered in init_csrf().
    Not called from route code.
    """
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    token: str = session["_csrf_token"]
    return token


def _csrf_field() -> str:
    """Return an HTML hidden input with the CSRF token.

    Called by: every template that renders a `<form method="post">`, as
    `{{ csrf_field() }}` — injected into Jinja's globals by init_csrf()'s
    context processor, so it's available everywhere without an explicit
    import. IMPORTANT for template authors: this must be placed *inside*
    the `<form>...</form>` tags it belongs to — placing it just after the
    closing `</form>` means the token never gets submitted and the form's
    POST is silently rejected by _validate_csrf() below (see BUG-018/H10 in
    devdocs/review-pr1-proof-scoring-noir.md — this hit the safe-word/pause
    form on coachee_dashboard.html among others; fixed, and
    tests/test_csrf_placement.py guards against regressions).
    """
    from markupsafe import Markup

    token = _generate_token()
    field: str = Markup(f'<input type="hidden" name="_csrf_token" value="{token}">')  # nosec B704 - token is server-generated via secrets.token_hex, not user input
    return field


def _validate_csrf():
    """Validate CSRF token on state-changing requests.

    Called by: Flask's before_request hook (registered in init_csrf(),
    called from app.py::create_app()) — runs before *every* route, on every
    POST/PUT/DELETE/PATCH. Not called directly by route code.
    """
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
    """Register CSRF protection on the Flask app.

    Called by: app.py::create_app() once, at process startup. Not called
    per-request.
    """
    app.before_request(_validate_csrf)
    app.context_processor(lambda: {"csrf_field": _csrf_field, "csrf_token": _generate_token})
