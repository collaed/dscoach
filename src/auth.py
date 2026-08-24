"""Authentication blueprint: login, logout, setup, register, features."""

from functools import wraps

from flask import Blueprint, redirect, render_template_string, request, session, url_for

from helpers import _audit, _hash, _hash_password, _real_ip, _tpl, _verify_password, db
from rate_limit import is_rate_limited, record_failed_attempt, reset_attempts

bp = Blueprint("auth", __name__)


def login_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session or session.get("role") != role:
                return redirect(url_for("auth.login"))
            return fn(*a, **kw)

        return wrapper

    return decorator


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user_id" not in session or session.get("role") != "coach" or not session.get("is_admin"):
            return redirect(url_for("auth.login"))
        return fn(*a, **kw)

    return wrapper


@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("coach.coach_dashboard" if session["role"] == "coach" else "coachee.coachee_dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
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
                c.execute("SELECT accent_color, bg_color, card_color, status FROM coach WHERE id=%s", (row["coach_id"],))
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
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
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
    return render_template_string(_tpl("features.html"))



@bp.route("/lang/<lang>")
def set_language(lang):
    """Switch UI language (en/fr)."""
    from i18n import SUPPORTED_LANGS

    if lang in SUPPORTED_LANGS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("auth.index"))


FONT_CHOICES = ("clean", "classic", "sharp", "modern")


@bp.route("/font/<font>")
def set_font(font):
    """Switch UI font preference."""
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
