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
    """Build database URL from environment variables."""
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
    """Get or create the global engine (singleton)."""
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
    """Get a new database connection."""
    return get_engine().connect()


def init_db():
    """Create all tables (idempotent) and seed admin account."""
    engine = get_engine()
    metadata.create_all(engine)
    _seed_admin(engine)


def _seed_admin(engine: Engine):
    """Ensure the ecb admin account exists."""
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
    """Seed demo coach (Kitsune) and coachee (severin)."""
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
    """Reset the engine (useful for tests)."""
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None
