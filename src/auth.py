"""Authentication blueprint: login, logout, setup, register, features."""

from functools import wraps

from flask import Blueprint, redirect, render_template_string, request, session, url_for
from helpers import _audit, _hash_password, _real_ip, _tpl, _verify_password, db
from rate_limit import is_rate_limited, record_failed_attempt, reset_attempts

bp = Blueprint("auth", __name__)


def login_required(role):
    """PURPOSE: Decorator factory guarding a route so only a session of the given role ("coach"/"coachee") may enter, else redirect to login.
    CALLED BY: Wraps route handlers across routes_coach.py, routes_coachee.py (/me* screens) and routes_admin.py; the returned wrapper runs per request.
    WHEN: On every request to a decorated route, before the handler executes."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session or session.get("role") != role:
                return redirect(url_for("auth.login"))
            return fn(*a, **kw)

        return wrapper

    return decorator


def admin_required(fn):
    """PURPOSE: Decorator guarding a route so only a logged-in coach with the is_admin flag may enter, else redirect to login.
    CALLED BY: Wraps every /admin* handler in routes_admin.py (admin dashboard, add/freeze/delete coach, reset password, support screens).
    WHEN: On every request to a decorated admin route, before the handler executes."""

    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session or session.get("role") != "coach" or not session.get("is_admin"):
            return redirect(url_for("auth.login"))
        return fn(*a, **kw)

    return wrapper


@bp.route("/")
def index():
    """PURPOSE: Root redirector — sends a logged-in user to their coach/coachee dashboard, otherwise to the login screen.
    CALLED BY: Route GET / — public landing entry; also target of url_for("auth.index") fallbacks in set_language/set_font.
    WHEN: On navigation to the site root."""
    if "user_id" in session:
        return redirect(url_for("coach.coach_dashboard" if session["role"] == "coach" else "coachee.coachee_dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """PURPOSE: Authenticate a coach or coachee, apply rate limiting, transparent argon2 rehash, seed session branding, and redirect to the right dashboard.
    CALLED BY: Route GET/POST /login — renders login.html; GET shows the form, POST processes credentials. Target of most redirect-to-login flows.
    WHEN: On visiting the login screen (GET) or submitting the login form (POST)."""
    err = ""
    if request.method == "POST":
        ip = _real_ip()
        if is_rate_limited(ip):
            err = "Too many failed attempts. Please wait 15 minutes."
            return render_template_string(_tpl("login.html"), error=err)

        username = request.form["username"]
        password = request.form["password"]
        c = db()
        # Try coach login
        c.execute(
            "SELECT id, name, timezone, accent_color, bg_color, card_color, is_admin, status, font_pref, password_hash FROM coach WHERE username=%s",
            (username,),
        )
        row = c.fetchone()
        if row:
            valid, needs_rehash = _verify_password(password, row["password_hash"])
            if valid:
                if row.get("status") == "frozen":
                    err = "Account frozen. Contact administrator."
                else:
                    # Transparent rehash to argon2 if still on SHA-256
                    if needs_rehash:
                        new_hash = _hash_password(password)
                        c.execute("UPDATE coach SET password_hash=%s WHERE id=%s", (new_hash, row["id"]))
                    reset_attempts(ip)
                    session.update(
                        user_id=row["id"],
                        role="coach",
                        name=row["name"],
                        timezone=row["timezone"] or "Europe/London",
                        accent=row["accent_color"] or "#e94560",
                        bg=row["bg_color"] or "#1a1a2e",
                        card=row["card_color"] or "#16213e",
                        is_admin=bool(row.get("is_admin")),
                        font_pref=row.get("font_pref") or "clean",
                    )
                    _audit("login", row["id"], "coach")
                    return redirect(url_for("coach.coach_dashboard"))
        # Try coachee login
        c.execute(
            "SELECT id, name, coach_id, color_scheme, avatar, font_pref, password_hash FROM coachee WHERE username=%s",
            (username,),
        )
        row = c.fetchone()
        if row:
            valid, needs_rehash = _verify_password(password, row["password_hash"])
            if valid:
                c.execute(
                    "SELECT accent_color, bg_color, card_color, status FROM coach WHERE id=%s", (row["coach_id"],)
                )
                coach_brand = c.fetchone()
                if coach_brand.get("status") == "frozen":
                    err = "Your coach's account is frozen."
                else:
                    # Transparent rehash to argon2 if still on SHA-256
                    if needs_rehash:
                        new_hash = _hash_password(password)
                        c.execute("UPDATE coachee SET password_hash=%s WHERE id=%s", (new_hash, row["id"]))
                    reset_attempts(ip)
                    session.update(
                        user_id=row["id"],
                        role="coachee",
                        name=row["name"],
                        coach_id=row["coach_id"],
                        accent=row["color_scheme"] or coach_brand["accent_color"] or "#e94560",
                        bg=coach_brand["bg_color"] or "#1a1a2e",
                        card=coach_brand["card_color"] or "#16213e",
                        avatar=row["avatar"] or "\U0001f415",
                        font_pref=row.get("font_pref") or "clean",
                    )
                    _audit("login", row["id"], "coachee")
                    # Track login count for onboarding
                    c.execute("UPDATE coachee SET login_count=COALESCE(login_count,0)+1 WHERE id=%s", (row["id"],))
                    return redirect(url_for("coachee.coachee_dashboard"))
        # Failed login
        record_failed_attempt(ip)
        err = "Invalid credentials"
    return render_template_string(_tpl("login.html"), error=err)


@bp.route("/logout")
def logout():
    """PURPOSE: Clear the session and return the user to the login screen.
    CALLED BY: Route GET /logout — logout link/button in coach, coachee and admin navigation templates.
    WHEN: On clicking logout."""
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """PURPOSE: First-run bootstrap — create the initial admin coach account; no-op redirect to login once any coach exists.
    CALLED BY: Route GET/POST /setup — renders setup.html; GET shows the form, POST inserts the first coach.
    WHEN: On visiting /setup during initial deployment before any coach is registered."""
    c = db()
    c.execute("SELECT COUNT(*) as cnt FROM coach")
    if c.fetchone()["cnt"] > 0:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        c.execute(
            "INSERT INTO coach (username, password_hash, name, timezone, is_admin) VALUES (%s,%s,%s,%s,1)",
            (
                request.form["username"],
                _hash_password(request.form["password"]),
                request.form["name"],
                request.form.get("timezone", "Europe/London"),
            ),
        )
        return redirect(url_for("auth.login"))
    return render_template_string(_tpl("setup.html"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    """PURPOSE: Self-service coach signup — validate inputs, ensure unique username, create a new (non-admin) coach account.
    CALLED BY: Route GET/POST /register — renders register.html; GET shows the form, POST creates the coach and redirects to login.
    WHEN: On visiting the register screen (GET) or submitting the signup form (POST)."""
    err = ""
    if request.method == "POST":
        c = db()
        username = request.form["username"].strip()
        name = request.form["name"].strip()
        pw = request.form["password"]
        tz = request.form.get("timezone", "Europe/London")
        if not username or not name or not pw:
            err = "All fields are required."
        elif len(pw) < 6:
            err = "Password must be at least 6 characters."
        else:
            c.execute("SELECT id FROM coach WHERE username=%s", (username,))
            if c.fetchone():
                err = "Username already taken."
            else:
                c.execute(
                    "INSERT INTO coach (username, password_hash, name, timezone) VALUES (%s,%s,%s,%s)",
                    (username, _hash_password(pw), name, tz),
                )
                new_id = c.lastrowid
                _audit("register", new_id, "coach")
                return redirect(url_for("auth.login"))
    return render_template_string(_tpl("register.html"), error=err)


@bp.route("/features")
def features_page():
    """PURPOSE: Render the public marketing/feature-overview page.
    CALLED BY: Route GET /features — public features.html screen, linked from login/register pages.
    WHEN: On navigation to /features."""
    return render_template_string(_tpl("features.html"))


@bp.route("/lang/<lang>")
def set_language(lang):
    """PURPOSE: Switch UI language (en/fr) by storing the choice in the session if supported.
    CALLED BY: Route GET /lang/<lang> — language switcher links in page footers/headers across all screens; redirects back to referrer.
    WHEN: On clicking a language toggle."""
    from i18n import SUPPORTED_LANGS

    if lang in SUPPORTED_LANGS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("auth.index"))


FONT_CHOICES = ("clean", "classic", "sharp", "modern")


@bp.route("/font/<font>")
def set_font(font):
    """PURPOSE: Switch UI font preference (clean/classic/sharp/modern) in the session and persist it to the coach/coachee row.
    CALLED BY: Route GET /font/<font> — font switcher links in page chrome across all screens; redirects back to referrer.
    WHEN: On clicking a font toggle."""
    if font not in FONT_CHOICES:
        return redirect(request.referrer or url_for("auth.index"))
    session["font_pref"] = font
    # Persist to DB
    if "user_id" in session:
        c = db()
        if session.get("role") == "coach":
            c.execute("UPDATE coach SET font_pref=%s WHERE id=%s", (font, session["user_id"]))
        elif session.get("role") == "coachee":
            c.execute("UPDATE coachee SET font_pref=%s WHERE id=%s", (font, session["user_id"]))
    return redirect(request.referrer or url_for("auth.index"))
