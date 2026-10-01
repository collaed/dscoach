"""Shared helpers for DSCoaching: DB access, hashing, template loading, auditing."""

import hashlib
import os
from datetime import UTC

from flask import g, request, session
from sqlalchemy import text

from database import get_db, get_engine
from models import audit_log as al_t

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
ATTACHMENTS_DIR = os.environ.get("ATTACHMENTS_DIR", "/data/attachments")

FLASH_STYLE = "<style>.flash{padding:.6rem 1rem;border-radius:6px;margin:.5rem 1rem;font-size:.9rem;text-align:center}.flash-success{background:#2d6a4f;color:#fff}.flash-error{background:#e94560;color:#fff}.flash-info{background:#16213e;color:#e0e0e0;border:1px solid #333}</style>"


def inject_helpers():
    """Make flash rendering and i18n available in all templates.

    PURPOSE: Build the {flash_block, t, lang, font_pref} context injected into every rendered template.
    CALLED BY: Registered as a Flask context_processor in app.py (create_app), so it runs for all screens (coach, coachee, admin, public).
    WHEN: On every template render, before Jinja evaluates the template.
    """
    from flask import get_flashed_messages as gfm

    from i18n import get_lang, t

    messages = gfm(with_categories=True)
    if messages:
        html = FLASH_STYLE + "".join(f'<div class="flash flash-{cat}">{msg}</div>' for cat, msg in messages)
    else:
        html = ""
    font_pref = session.get("font_pref", "clean")
    return {"flash_block": html, "t": t, "lang": get_lang(), "font_pref": font_pref}


def _real_ip():
    """Get real client IP from Cloudflare/proxy headers, falling back to remote_addr.

    PURPOSE: Resolve the true client IP behind Caddy/Cloudflare for audit logging.
    CALLED BY: _audit (helpers.py) and the login route in auth.py (POST /login) — feeds IP into the audit_log table across all screens.
    WHEN: Whenever an auditable action or login is processed, on form submit / request handling.
    """
    return (
        request.headers.get("Cf-Connecting-Ip")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
    )


def _audit(action, user_id=None, role=None):
    """Best-effort insert of an action into the audit_log table (never raises).

    PURPOSE: Record who did what, with IP and user-agent, for security/traceability.
    CALLED BY: Route handlers in auth.py (login/logout), routes_coach.py, and routes_admin.py (add/freeze/delete coach, password resets) — logs actions across coach and admin screens.
    WHEN: On form submit / privileged action; failures are silently swallowed so auditing never breaks a request.
    """
    try:
        conn = db()
        conn.execute(
            al_t.insert().values(
                user_id=user_id or session.get("user_id", 0),
                role=role or session.get("role", ""),
                action=action,
                ip=_real_ip(),
                user_agent=str(request.user_agent)[:500],
            )
        )
        conn.commit()
    except Exception:
        pass


def _hash(pw):
    """Legacy SHA-256 hash. Used for backward compatibility only.

    PURPOSE: Produce a SHA-256 hex digest of a password (superseded by _hash_password/argon2).
    CALLED BY: Imported by auth.py and routes_coach.py for legacy seeded/admin hashes; new hashing goes through _hash_password.
    WHEN: On credential comparison/seeding paths that still expect the old SHA-256 format.
    """
    return hashlib.sha256(pw.encode()).hexdigest()


def utcnow():
    """Return the current UTC time as a timezone-aware datetime.

    PURPOSE: Single source of aware "now" for timestamps and filenames.
    CALLED BY: routes_coach.py, routes_coachee.py, routes_admin.py, merge.py, photo_validation.py, services/freeze.py — used for check-in/attachment timestamps and freeze cutoffs across coach, coachee, and admin screens.
    WHEN: On form submit / any request needing the current instant.
    """
    from datetime import datetime

    return datetime.now(UTC)


def ensure_aware(dt):
    """Ensure a datetime is timezone-aware. Assumes UTC if naive.

    PURPOSE: Normalize DB-loaded datetimes (which may be naive strings) to aware UTC for safe comparison.
    CALLED BY: routes_coachee.py in the task-submit handler (POST /me/task/<tid>) to compare a task's frozen_after against utcnow() — serves the coachee task screen.
    WHEN: On coachee task submit, before deciding if a task is past its freeze cutoff.
    """
    from datetime import datetime

    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _hash_password(pw):
    """Hash a password with argon2id (preferred) or SHA-256 fallback.

    PURPOSE: Produce a secure password hash for storage in coach/coachee tables.
    CALLED BY: auth.py (setup/register/login rehash), routes_coach.py (change-password, coachee reset-password, add coachee), routes_admin.py (add coach, reset password) — serves auth, coach, and admin screens.
    WHEN: On account creation, password change, or transparent rehash after a successful login with a legacy hash.
    """
    try:
        from argon2 import PasswordHasher

        ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
        return ph.hash(pw)
    except ImportError:
        # argon2-cffi not available, fall back to SHA-256
        return hashlib.sha256(pw.encode()).hexdigest()


def _verify_password(pw, stored_hash):
    """Verify a password against a stored hash. Supports argon2id and SHA-256.

    PURPOSE: Check a submitted password and signal whether the stored hash should be upgraded.
    CALLED BY: auth.py login handler (POST /login for coach and coachee) and routes_coach.py change-password/change-name handlers — serves the login and coach settings screens.
    WHEN: On login submit and on coach password-change submit.

    Returns (is_valid, needs_rehash):
        - is_valid: True if the password matches
        - needs_rehash: True if the stored hash is SHA-256 and should be upgraded
    """
    if stored_hash.startswith("$argon2"):
        # argon2id hash
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError

            ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
            try:
                ph.verify(stored_hash, pw)
                # Check if params need updating
                return True, ph.check_needs_rehash(stored_hash)
            except VerifyMismatchError:
                return False, False
        except ImportError:
            return False, False
    else:
        # Legacy SHA-256 hash (64 hex chars)
        sha_hash = hashlib.sha256(pw.encode()).hexdigest()
        if sha_hash == stored_hash:
            return True, True  # Valid but needs rehash to argon2
        return False, False


def _rand_func():
    """Return the random ordering SQL fragment appropriate for the current DB engine.

    PURPOSE: Yield RAND()/RANDOM() keyword so ORDER BY works portably across MySQL, PostgreSQL, and SQLite.
    CALLED BY: tasks.py _auto_assign_reserves (reserve-task selection) — feeds the coachee dashboard (GET /me) auto-assignment logic.
    WHEN: On coachee dashboard load, when picking a random reserve task.
    """
    dialect = get_engine().dialect.name
    if dialect == "mysql":
        return "RAND()"
    return "RANDOM()"


def _now_func():
    """Return NOW() equivalent for the current dialect.

    PURPOSE: Yield the dialect-correct current-timestamp SQL keyword (CURRENT_TIMESTAMP on SQLite, NOW() otherwise).
    CALLED BY: A portable-SQL utility alongside _rand_func; not currently referenced by any route (Python utcnow() is preferred for timestamps). Kept for dialect-transparent SQL per project conventions.
    WHEN: Would be invoked when building raw SQL that needs a server-side "now" fragment.
    """
    dialect = get_engine().dialect.name
    if dialect == "sqlite":
        return "CURRENT_TIMESTAMP"
    return "NOW()"


def _tpl(name):
    """Read a template file's raw text from the templates/ directory.

    PURPOSE: Load a Jinja2 template source string for render_template_string.
    CALLED BY: Nearly every route handler in auth.py, routes_coach.py, routes_coachee.py, routes_admin.py (e.g. _tpl("coach_dashboard.html"), _tpl("login.html")) — supplies markup for all coach, coachee, admin, and public screens.
    WHEN: On each request that renders a screen, immediately before render_template_string.
    """
    with open(os.path.join(TEMPLATES_DIR, name)) as f:
        return f.read()


def _convert_placeholders(sql):
    """Convert %s style placeholders to :p0, :p1, ... named params.

    PURPOSE: Translate the app's `%s` positional SQL style into SQLAlchemy named params for portability.
    CALLED BY: _SAConn.execute (helpers.py) whenever raw SQL text is executed — underlies every db() query across all screens.
    WHEN: On each raw-SQL execution, before the statement is sent to the engine.
    """
    parts = sql.split("%s")
    if len(parts) == 1:
        return sql
    result = parts[0]
    for i, part in enumerate(parts[1:]):
        result += f":p{i}" + part
    return result


def _params_to_dict(sql, params):
    """Convert positional params tuple to named dict {p0: val, p1: val, ...}.

    PURPOSE: Map a positional params tuple to the named-param dict expected after placeholder conversion.
    CALLED BY: _SAConn.execute (helpers.py), paired with _convert_placeholders on every raw-SQL query — underlies all db() queries across all screens.
    WHEN: On each raw-SQL execution, before the statement is sent to the engine.
    """
    if not params:
        return {}
    if isinstance(params, dict):
        return params
    return {f"p{i}": v for i, v in enumerate(params)}


class _SAConn:
    """Wrapper around SQLAlchemy connection that provides dict-like row access.

    PURPOSE: Adapt a raw SQLAlchemy connection to the app's %s-placeholder + dict-row query style.
    CALLED BY: Instantiated by db() (helpers.py); its instance is what every route/service uses for queries across all screens.
    WHEN: Created lazily once per request when db() is first called.
    """

    def __init__(self, conn):
        """Wrap a raw SQLAlchemy connection.

        PURPOSE: Store the underlying connection for later execute/commit/close.
        CALLED BY: db() (helpers.py) when opening a per-request connection.
        WHEN: On the first db() call within a request.
        """
        self._conn = conn

    def execute(self, query, params=None):
        """Execute raw SQL text or SQLAlchemy expression. Returns self for chaining.

        PURPOSE: Run a query, converting %s placeholders and positional params when the query is a string.
        CALLED BY: Every route handler and service via db().execute(...) across coach, coachee, admin, and public screens.
        WHEN: On each database read/write during request handling.
        """
        if isinstance(query, str):
            self._result = self._conn.execute(text(_convert_placeholders(query)), _params_to_dict(query, params))
        else:
            self._result = self._conn.execute(query, params or {})
        return self

    def fetchone(self):
        """Return the next result row as a dict, or None.

        PURPOSE: Provide dict-like access to a single query row.
        CALLED BY: Route handlers/services after db().execute(...) when a single record is expected, across all screens.
        WHEN: Immediately after an execute() that selects one row.
        """
        row = self._result.fetchone()
        return dict(row._mapping) if row else None

    def fetchall(self):
        """Return all result rows as a list of dicts.

        PURPOSE: Provide dict-like access to a full result set.
        CALLED BY: Route handlers/services after db().execute(...) when listing records (e.g. dashboards, task lists), across all screens.
        WHEN: Immediately after an execute() that selects multiple rows.
        """
        return [dict(r._mapping) for r in self._result.fetchall()]

    @property
    def lastrowid(self):
        """Return the primary key of the most recent INSERT (dialect-tolerant).

        PURPOSE: Recover the auto-generated id after an insert across SQLite/PostgreSQL/MySQL.
        CALLED BY: Route handlers/services that need the new row id after db().execute(INSERT ...), e.g. creating tasks, notes, or coachees.
        WHEN: Right after an INSERT during request handling.
        """
        try:
            return self._result.lastrowid
        except AttributeError:
            try:
                pk = self._result.inserted_primary_key
                return pk[0] if pk else None
            except AttributeError:
                return None

    def commit(self):
        """Commit the underlying connection.

        PURPOSE: Persist pending changes (mostly a no-op given AUTOCOMMIT engine config).
        CALLED BY: _audit (helpers.py) and any handler that explicitly commits; invoked via db().commit().
        WHEN: After a write when an explicit commit is issued.
        """
        self._conn.commit()

    def close(self):
        """Close the underlying connection.

        PURPOSE: Release the raw SQLAlchemy connection.
        CALLED BY: close_db (helpers.py) at request teardown; the raw connection is closed there via g._raw_conn.
        WHEN: At the end of each request.
        """
        self._conn.close()


def db():
    """Return the per-request database connection wrapper, opening it on first use.

    PURPOSE: Provide a cached _SAConn (dict-row, %s-placeholder) bound to Flask's request-scoped g.
    CALLED BY: Every route handler and service (auth.py, routes_coach.py, routes_coachee.py, routes_admin.py, tasks.py, automation.py, merge.py, etc.) — underlies all coach, coachee, admin, and public screens.
    WHEN: On the first db() call within a request; reused for the rest of that request.
    """
    if "db" not in g:
        conn = get_db()
        g.db = _SAConn(conn)
        g._raw_conn = conn
    return g.db


def close_db(exc):
    """Close and clear the request-scoped database connection.

    PURPOSE: Release the connection stored on g at the end of the request.
    CALLED BY: Registered via app.teardown_appcontext(close_db) in app.py (create_app) — runs for all screens.
    WHEN: On Flask app-context teardown, after each request finishes.
    """
    conn = g.pop("_raw_conn", None)
    g.pop("db", None)
    if conn:
        conn.close()
