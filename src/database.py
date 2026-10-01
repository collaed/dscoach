"""Database engine and connection management for DSCoaching.

Supports MySQL (Wasmer Edge), PostgreSQL (Docker dev), and SQLite (tests).
Backend is selected via DATABASE_URL env var or constructed from DB_* vars.
"""

import hashlib
import os

from models import coach, metadata
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# --- Engine construction ---

_engine: Engine | None = None


def _build_url() -> str:
    """Build database URL from environment variables.

    Called by: get_engine() only, at first connection. Not screen-facing —
    read once per process at startup (or first request in a fresh worker).
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Legacy env var support (Wasmer Edge style)
    engine = os.environ.get("DB_ENGINE", "mysql")
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3306" if engine == "mysql" else "5432")
    user = os.environ.get("DB_USERNAME", "root")
    password = os.environ.get("DB_PASSWORD", "")
    dbname = os.environ.get("DB_NAME", "coaching")

    if engine == "mysql":
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"
    elif engine == "postgresql":
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    elif engine == "sqlite":
        path = os.environ.get("DB_PATH", ":memory:")
        return f"sqlite:///{path}" if path != ":memory:" else "sqlite://"
    else:
        raise ValueError(f"Unsupported DB_ENGINE: {engine}")


def get_engine() -> Engine:
    """Get or create the global engine (singleton).

    Called by: get_db() (every request, via helpers.db()) and init_db() at
    startup. Not called directly from route code.
    """
    global _engine
    if _engine is None:
        url = _build_url()
        kwargs = {"pool_pre_ping": True, "isolation_level": "AUTOCOMMIT"}
        if url.startswith("sqlite"):
            # SQLite doesn't support pool_pre_ping
            kwargs = {"isolation_level": "AUTOCOMMIT"}
        _engine = create_engine(url, **kwargs)
    return _engine


def get_db():
    """Get a new database connection.

    Called by: helpers.py::db() once per request (Flask `g` cache), which is
    what every route in routes_coach.py / routes_coachee.py / routes_admin.py
    / auth.py actually imports and calls (`c = db()`). Also called directly
    by scripts/seed_dev.py and by tests' conftest fixtures. Not called
    directly from route code — always go through helpers.db().
    """
    return get_engine().connect()


def init_db():
    """Create all tables (idempotent) and seed admin account.

    Called by: app.py::create_app() at process startup (every worker boot,
    every `flask run`, every container start) — this is what makes the app
    self-provisioning on a fresh database. Also called by scripts/seed_dev.py
    and test fixtures (tests/conftest.py) before each test to reset schema.
    Not screen-facing; runs before any request is served.
    """
    engine = get_engine()
    metadata.create_all(engine)
    _seed_admin(engine)


def _seed_admin(engine: Engine):
    """Ensure the ecb admin account exists.

    Called by: init_db() only, on every startup — idempotent (updates the
    row if it already exists rather than erroring). This is what guarantees
    the /login screen always has at least one working admin account, even on
    a brand-new empty database. Also seeds the Kitsune/severin demo pair via
    _seed_demo_users() unless DB_ENGINE=sqlite (tests) or SKIP_DEMO_SEED is set.
    """
    ecb_hash = hashlib.sha256(b"ecbF3T").hexdigest()
    with engine.begin() as conn:
        result = conn.execute(coach.select().where(coach.c.username == "ecb"))
        row = result.fetchone()
        if not row:
            conn.execute(
                coach.insert().values(
                    username="ecb",
                    password_hash=ecb_hash,
                    name="ECB Admin",
                    timezone="Europe/Brussels",
                    is_admin=1,
                )
            )
        else:
            conn.execute(coach.update().where(coach.c.username == "ecb").values(is_admin=1, password_hash=ecb_hash))

        # Ensure at least one admin exists
        result = conn.execute(text("SELECT COUNT(*) FROM coach WHERE is_admin=1"))
        if result.scalar() == 0:
            conn.execute(text("UPDATE coach SET is_admin=1 WHERE id=(SELECT MIN(id) FROM (SELECT id FROM coach) AS t)"))

    # Only seed demo users in non-test environments
    url = _build_url()
    if not url.startswith("sqlite://") and not os.environ.get("SKIP_DEMO_SEED"):
        _seed_demo_users(engine)


def _seed_demo_users(engine: Engine):
    """Seed demo coach (Kitsune) and coachee (severin).

    Called by: _seed_admin() only, and only against a real (non-SQLite)
    database with demo-seeding not explicitly disabled. Exists so a fresh
    Docker/local-dev deploy has a working coach+coachee pair to log into and
    click around the /coach and /me screens without manually registering.
    Not used in production seeding (SKIP_DEMO_SEED should be set there).
    """
    from models import coachee

    kitsune_hash = hashlib.sha256(b"Goddess").hexdigest()
    severin_hash = hashlib.sha256(b"ecbS3V").hexdigest()

    with engine.begin() as conn:
        # Create coach Kitsune
        result = conn.execute(coach.select().where(coach.c.username == "Kitsune"))
        row = result.fetchone()
        if not row:
            conn.execute(
                coach.insert().values(
                    username="Kitsune",
                    password_hash=kitsune_hash,
                    name="Kitsune",
                    timezone="Europe/Brussels",
                    is_admin=0,
                )
            )
        else:
            conn.execute(coach.update().where(coach.c.username == "Kitsune").values(password_hash=kitsune_hash))

        # Get Kitsune's ID for coachee FK
        result = conn.execute(coach.select().where(coach.c.username == "Kitsune"))
        kitsune_row = result.fetchone()
        assert kitsune_row is not None  # just inserted or updated above
        kitsune_id = kitsune_row[0]  # id is first column

        # Create coachee severin under Kitsune
        result = conn.execute(coachee.select().where(coachee.c.username == "severin"))
        row = result.fetchone()
        if not row:
            conn.execute(
                coachee.insert().values(
                    username="severin",
                    password_hash=severin_hash,
                    name="Severin",
                    coach_id=kitsune_id,
                    timezone="Europe/Brussels",
                )
            )
        else:
            conn.execute(coachee.update().where(coachee.c.username == "severin").values(password_hash=severin_hash))


def reset_engine():
    """Reset the engine (useful for tests).

    Called by: tests/conftest.py's reset_db fixture, before and after every
    test, so each test gets a fresh SQLite in-memory engine (a shared engine
    would leak schema/data between tests since sqlite:// in-memory is
    per-connection). Not called from application/route code.
    """
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None
