"""DSCoaching application factory."""

import os
import secrets

from flask import Flask, render_template_string

from database import init_db
from helpers import TEMPLATES_DIR, close_db, inject_helpers

def create_app():
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
        with open(os.path.join(TEMPLATES_DIR, name)) as f:
            return f.read()

    @application.errorhandler(404)
    def not_found(e):
        return render_template_string(_tpl("error.html"), code=404, msg="Page not found"), 404

    @application.errorhandler(403)
    def forbidden(e):
        return render_template_string(_tpl("error.html"), code=403, msg="Access denied"), 403

    @application.errorhandler(500)
    def server_error(e):
        return render_template_string(_tpl("error.html"), code=500, msg="Something went wrong"), 500

    with application.app_context():
        try:
            init_db()
        except Exception as e:
            print(f"DB init warning: {e}")

    return application


# Module-level app instance for backward compatibility (tests import `from app import app`)
app = create_app()
