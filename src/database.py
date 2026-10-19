"""Database engine and connection management for DSCoaching.

Supports MySQL (Wasmer Edge), PostgreSQL (Docker dev), and SQLite (tests).
Backend is selected via DATABASE_URL env var or constructed from DB_* vars.
"""

import hashlib
import json
import os

from models import coach, contract_section, contract_section_task, metadata
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SEED_DATA_DIR = os.path.join(os.path.dirname(__file__), "seed_data")

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
    _seed_contract_library(engine)


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


def _seed_contract_library(engine: Engine):
    """R52: seed the system-default (coach_id=NULL) contract section library once.

    Called by: init_db() only, on every startup - idempotent (a no-op once any
    coach_id=NULL section exists, so a coach's own edits/deletes of their private
    sections are never touched and this never re-seeds on restart). Source data:
    seed_data/contract_library_seed.json, genericized from a real contract (see
    devdocs/plan-contract-drafting.md §2). Each sample task is attached to the
    FIRST of its linked_contract_sections only - the schema (and REQ-52.3) models
    one section per task; the source data's few multi-section tasks lose that
    extra association, not the task itself. The one task with no link at all
    is homed under section 0 (overview) rather than dropped.
    """
    with engine.begin() as conn:
        already_seeded = conn.execute(text("SELECT 1 FROM contract_section WHERE coach_id IS NULL LIMIT 1")).fetchone()
        if already_seeded:
            return

        seed_path = os.path.join(SEED_DATA_DIR, "contract_library_seed.json")
        with open(seed_path, encoding="utf-8") as f:
            data = json.load(f)

        # Best-effort category per section (the source data carries no category field -
        # see devdocs/plan-contract-drafting.md). Anything not listed falls back to 'custom'.
        category_by_order = {
            0: "foundation",
            1: "roles",
            2: "roles",
            3: "consent",
            4: "time",
            5: "ritual",
            6: "ritual",
            8: "service",
            10: "ritual",
            12: "evaluation",
            13: "rewards",
            14: "physical",
            15: "physical",
            16: "evaluation",
            17: "evaluation",
            18: "ritual",
            19: "dissolution",
        }

        # The source JSON's placeholder is {{coachee_name}}; merge.py's actual
        # vocabulary (merge.py::_get_merge_context) calls the same value {{name}}.
        # Rewrite at seed time rather than teach merge.py a second name for one thing.
        def _to_merge_vocab(text):
            return text.replace("{{coachee_name}}", "{{name}}")

        order_to_id = {}
        for section in data["contract_sections"]:
            result = conn.execute(
                contract_section.insert().values(
                    coach_id=None,
                    title=section["title"],
                    category=category_by_order.get(section["order"], "custom"),
                    body=_to_merge_vocab(section["content_template"]),
                    reusability=section["reusability"],
                    sort_hint=section["order"],
                )
            )
            order_to_id[section["order"]] = result.inserted_primary_key[0]

        for task in data["sample_tasks"]:
            # Tasks link to 1+ sections in the source data; the schema (REQ-52.3) models
            # one section per task, so take the first. A few carry no link at all - home
            # those under section 0 (overview) rather than silently dropping a real task.
            linked = task.get("linked_contract_sections") or [0]
            section_id = order_to_id.get(linked[0])
            if section_id is None:
                continue
            conn.execute(
                contract_section_task.insert().values(
                    section_id=section_id,
                    title=task["title"],
                    description=_to_merge_vocab(task.get("description_template", "")),
                    recurrence=task.get("recurrence", "once"),
                    proof_pct=task.get("suggested_proof_pct", 0),
                    points=task.get("suggested_points", 0),
                )
            )


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
