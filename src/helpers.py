"""Shared helpers for DSCoaching: DB access, hashing, template loading, auditing."""

import hashlib
import os

from flask import g, render_template_string, request, session
from database import get_db, get_engine
from models import audit_log as al_t
from sqlalchemy import text

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
ATTACHMENTS_DIR = os.environ.get("ATTACHMENTS_DIR", "/data/attachments")

FLASH_STYLE = "<style>.flash{padding:.6rem 1rem;border-radius:6px;margin:.5rem 1rem;font-size:.9rem;text-align:center}.flash-success{background:#2d6a4f;color:#fff}.flash-error{background:#e94560;color:#fff}.flash-info{background:#16213e;color:#e0e0e0;border:1px solid #333}</style>"


def inject_helpers():
    """Make flash rendering and i18n available in all templates."""
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
    """Get real client IP from Cloudflare/proxy headers, falling back to remote_addr."""
    return (
        request.headers.get("Cf-Connecting-Ip")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
    )


def _audit(action, user_id=None, role=None):
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
    """Legacy SHA-256 hash. Used for backward compatibility only."""
    return hashlib.sha256(pw.encode()).hexdigest()


def utcnow():
    """Return the current UTC time as a timezone-aware datetime."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def ensure_aware(dt):
    """Ensure a datetime is timezone-aware. Assumes UTC if naive."""
    from datetime import datetime, timezone
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hash_password(pw):
    """Hash a password with argon2id (preferred) or SHA-256 fallback."""
    try:
        from argon2 import PasswordHasher

        ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
        return ph.hash(pw)
    except ImportError:
        # argon2-cffi not available, fall back to SHA-256
        return hashlib.sha256(pw.encode()).hexdigest()


def _verify_password(pw, stored_hash):
    """Verify a password against a stored hash. Supports argon2id and SHA-256.

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
    """Return the random ordering SQL fragment appropriate for the current DB engine."""
    dialect = get_engine().dialect.name
    if dialect == "mysql":
        return "RAND()"
    return "RANDOM()"


def _now_func():
    """Return NOW() equivalent for the current dialect."""
    dialect = get_engine().dialect.name
    if dialect == "sqlite":
        return "CURRENT_TIMESTAMP"
    return "NOW()"


def _tpl(name):
    with open(os.path.join(TEMPLATES_DIR, name)) as f:
        return f.read()


def _convert_placeholders(sql):
    """Convert %s style placeholders to :p0, :p1, ... named params."""
    parts = sql.split("%s")
    if len(parts) == 1:
        return sql
    result = parts[0]
    for i, part in enumerate(parts[1:]):
        result += f":p{i}" + part
    return result


def _params_to_dict(sql, params):
    """Convert positional params tuple to named dict {p0: val, p1: val, ...}."""
    if not params:
        return {}
    if isinstance(params, dict):
        return params
    return {f"p{i}": v for i, v in enumerate(params)}


class _SAConn:
    """Wrapper around SQLAlchemy connection that provides dict-like row access."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        """Execute raw SQL text or SQLAlchemy expression. Returns self for chaining."""
        if isinstance(query, str):
            self._result = self._conn.execute(text(_convert_placeholders(query)), _params_to_dict(query, params))
        else:
            self._result = self._conn.execute(query, params or {})
        return self

    def fetchone(self):
        row = self._result.fetchone()
        return dict(row._mapping) if row else None

    def fetchall(self):
        return [dict(r._mapping) for r in self._result.fetchall()]

    @property
    def lastrowid(self):
        try:
            return self._result.lastrowid
        except AttributeError:
            try:
                pk = self._result.inserted_primary_key
                return pk[0] if pk else None
            except AttributeError:
                return None

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def db():
    if "db" not in g:
        conn = get_db()
        g.db = _SAConn(conn)
        g._raw_conn = conn
    return g.db


def close_db(exc):
    conn = g.pop("_raw_conn", None)
    g.pop("db", None)
    if conn:
        conn.close()
