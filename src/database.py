"""Database engine and connection management for DSCoaching.

Supports PostgreSQL (production/dev) and SQLite (tests).
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
    """PURPOSE: Build the SQLAlchemy database URL from DATABASE_URL or legacy DB_* env vars
    (mysql/postgresql/sqlite).
    CALLED BY / SCREEN: get_engine() and _seed_admin() in this module; indirectly serves every
    screen via DB access.
    WHEN: on first engine creation at startup, and on each _seed_admin demo-seed check."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Legacy env var support
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
    """PURPOSE: Get or lazily create the process-wide SQLAlchemy engine (singleton, AUTOCOMMIT).
    CALLED BY / SCREEN: get_db(), init_db() here and helpers.py (dialect checks) — underpins all screens.
    WHEN: on first DB access at startup, then reused for the process lifetime."""
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
    """PURPOSE: Open a new connection from the shared engine.
    CALLED BY / SCREEN: helpers.db() (request-scoped connection cache) which every route/service
    uses — serves all screens.
    WHEN: on first DB use within a request; connection is cached per request via helpers."""
    return get_engine().connect()


def init_db():
    """PURPOSE: Create all tables (idempotent) and seed the admin account.
    CALLED BY / SCREEN: create_app() in app.py within the app context — bootstraps the DB for all screens.
    WHEN: once at app-creation / process startup."""
    engine = get_engine()
    metadata.create_all(engine)
    _seed_admin(engine)


def _seed_admin(engine: Engine):
    """PURPOSE: Ensure the `ecb` admin coach account exists and at least one admin is present;
    seeds demo users in non-test environments.
    CALLED BY / SCREEN: init_db() at startup — enables the admin/login screens.
    WHEN: once at startup, after table creation."""
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
    """PURPOSE: Seed the demo coach (Kitsune) and demo coachee (severin under Kitsune).
    CALLED BY / SCREEN: _seed_admin() in non-test (non-sqlite) environments — populates the
    coach/coachee login and dashboard screens with demo data.
    WHEN: once at startup, unless SKIP_DEMO_SEED is set or running on sqlite (tests)."""
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
    """PURPOSE: Dispose and clear the singleton engine so the next get_engine() rebuilds it.
    CALLED BY / SCREEN: test fixtures (tests/) to reset DB state between test modules; no
    end-user screen.
    WHEN: between tests / when the engine must be recreated (e.g. changed DB env)."""
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None
