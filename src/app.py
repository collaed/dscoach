"""DSCoaching application factory."""

import os
import secrets

from database import init_db
from flask import Flask, render_template_string
from helpers import TEMPLATES_DIR, close_db, inject_helpers


def create_app():
    """PURPOSE: Build and configure the Flask app (session cookies, teardown, context
    processor, CSRF, blueprints, error handlers, DB init).
    CALLED BY / SCREEN: module-level `app = create_app()` at bottom of app.py; imported by
    server.py/server_docker.py (WSGI entry) and by tests (`from app import app`). Serves all screens.
    WHEN: once at app-creation / process startup."""
    application = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
    )
    application.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    application.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    application.config["SESSION_COOKIE_HTTPONLY"] = True

    application.teardown_appcontext(close_db)
    application.context_processor(inject_helpers)

    # CSRF protection
    from csrf import init_csrf

    init_csrf(application)

    from auth import bp as auth_bp
    from routes_admin import bp as admin_bp
    from routes_coach import bp as coach_bp
    from routes_coachee import bp as coachee_bp

    application.register_blueprint(auth_bp)
    application.register_blueprint(coach_bp)
    application.register_blueprint(coachee_bp)
    application.register_blueprint(admin_bp)

    def _tpl(name):
        """PURPOSE: Read a raw template file from TEMPLATES_DIR for render_template_string.
        CALLED BY / SCREEN: the not_found/forbidden/server_error error handlers below, to load
        error.html for the 404/403/500 error screens.
        WHEN: on each error-handler invocation (when an error response is rendered)."""
        with open(os.path.join(TEMPLATES_DIR, name)) as f:
            return f.read()

    @application.errorhandler(404)
    def not_found(e):
        """PURPOSE: Render the styled error.html page with a 404 status.
        CALLED BY / SCREEN: Flask error dispatch for unmatched URLs — serves the 404 error screen.
        WHEN: whenever a request hits a non-existent route."""
        return render_template_string(_tpl("error.html"), code=404, msg="Page not found"), 404

    @application.errorhandler(403)
    def forbidden(e):
        """PURPOSE: Render the styled error.html page with a 403 status.
        CALLED BY / SCREEN: Flask error dispatch on aborted requests (e.g. CSRF/auth abort(403)) —
        serves the 403 access-denied error screen.
        WHEN: whenever a request is forbidden (CSRF failure, auth guard, explicit abort(403))."""
        return render_template_string(_tpl("error.html"), code=403, msg="Access denied"), 403

    @application.errorhandler(500)
    def server_error(e):
        """PURPOSE: Render the styled error.html page with a 500 status.
        CALLED BY / SCREEN: Flask error dispatch on unhandled exceptions — serves the 500 error screen.
        WHEN: whenever a request raises an unhandled server error."""
        return render_template_string(_tpl("error.html"), code=500, msg="Something went wrong"), 500

    with application.app_context():
        try:
            init_db()
        except Exception as e:
            print(f"DB init warning: {e}")

    return application


# Module-level app instance for backward compatibility (tests import `from app import app`)
app = create_app()
