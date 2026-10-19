"""Tests for R52: contract section library, drafting, and sample-task creation."""

from database import get_engine
from sqlalchemy import text


def _add_coachee(client, username="draftsub"):
    client.post(
        "/coach/coachee/add",
        data={
            "username": username,
            "password": "pass123",
            "name": "Draft Sub",
            "contract": "",
            "safe_word": "RED",
            "task_unveil_time": "00:01",
            "task_freeze_time": "22:00",
            "timezone": "UTC",
        },
    )
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM coachee WHERE username=:u"), {"u": username}).scalar()


def test_system_default_library_is_seeded(client):
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM contract_section WHERE coach_id IS NULL")).scalar()
        task_count = conn.execute(text("SELECT COUNT(*) FROM contract_section_task")).scalar()
    assert count == 20
    assert task_count == 23


def test_seeded_sections_use_mergepy_vocabulary_not_raw_coachee_name(client):
    """The source JSON's {{coachee_name}} placeholder must be rewritten to {{name}}
    at seed time - merge.py only knows {{name}}, so a raw {{coachee_name}} would
    survive _merge_vars() untouched and show up literally in an assembled contract.
    """
    engine = get_engine()
    with engine.connect() as conn:
        leftover_sections = conn.execute(
            text("SELECT COUNT(*) FROM contract_section WHERE body LIKE '%{{coachee_name}}%'")
        ).scalar()
        leftover_tasks = conn.execute(
            text("SELECT COUNT(*) FROM contract_section_task WHERE description LIKE '%{{coachee_name}}%'")
        ).scalar()
    assert leftover_sections == 0
    assert leftover_tasks == 0


def test_seeding_is_idempotent_across_init_db_calls(client):
    from database import init_db

    init_db()
    init_db()
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM contract_section WHERE coach_id IS NULL")).scalar()
    assert count == 20


def test_coach_can_create_own_section(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post("/coach/contract-sections", data={"action": "create", "title": "My Section", "body": "Hello {{name}}"})
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT coach_id FROM contract_section WHERE title='My Section'")).fetchone()
    assert row[0] == 1


def test_coach_can_clone_a_default(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    engine = get_engine()
    with engine.connect() as conn:
        default_id = conn.execute(text("SELECT id FROM contract_section WHERE coach_id IS NULL LIMIT 1")).scalar()
    client.post("/coach/contract-sections", data={"action": "clone", "section_id": str(default_id)})
    with engine.connect() as conn:
        clone = conn.execute(
            text("SELECT coach_id, title FROM contract_section WHERE coach_id=1 AND title LIKE '%(copy)'")
        ).fetchone()
    assert clone is not None


def test_coach_cannot_delete_a_system_default(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    engine = get_engine()
    with engine.connect() as conn:
        default_id = conn.execute(text("SELECT id FROM contract_section WHERE coach_id IS NULL LIMIT 1")).scalar()
    client.post("/coach/contract-sections", data={"action": "delete", "section_id": str(default_id)})
    with engine.connect() as conn:
        still_there = conn.execute(text("SELECT 1 FROM contract_section WHERE id=:i"), {"i": default_id}).fetchone()
    assert still_there is not None


def test_non_owning_coach_cannot_delete_or_update_anothers_section(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post("/coach/contract-sections", data={"action": "create", "title": "Private A", "body": "x"})
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach6", "password": "pass123", "name": "Other Coach 6", "timezone": "UTC"},
    )
    client.get("/logout")

    engine = get_engine()
    with engine.connect() as conn:
        sid = conn.execute(text("SELECT id FROM contract_section WHERE title='Private A'")).scalar()

    client.post("/login", data={"username": "othercoach6", "password": "pass123"})
    client.post("/coach/contract-sections", data={"action": "delete", "section_id": str(sid)})
    client.post(
        "/coach/contract-sections", data={"action": "update", "section_id": str(sid), "title": "Hijacked", "body": "x"}
    )

    with engine.connect() as conn:
        row = conn.execute(text("SELECT title FROM contract_section WHERE id=:i"), {"i": sid}).fetchone()
    assert row[0] == "Private A"


def test_draft_assemble_merges_coach_name_and_coachee_name(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(
        "/coach/contract-sections",
        data={"action": "create", "title": "Greeting", "body": "Hello {{name}}, this is {{coach_name}}."},
    )
    engine = get_engine()
    with engine.connect() as conn:
        sid = conn.execute(text("SELECT id FROM contract_section WHERE title='Greeting'")).scalar()

    resp = client.post(
        f"/coach/coachee/{cid}/contract/draft",
        data={"action": "assemble", "section_ids": [str(sid)]},
    )
    assert resp.status_code == 200
    assert b"Hello Draft Sub, this is ECB Admin." in resp.data
    assert b"{{name}}" not in resp.data


def test_draft_save_updates_contract_text_and_versions_old_one(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE coachee SET contract_text='old text' WHERE id=:c"), {"c": cid})

    resp = client.post(
        f"/coach/coachee/{cid}/contract/draft",
        data={"action": "save", "assembled_text": "brand new contract text"},
    )
    assert resp.status_code == 302
    with engine.connect() as conn:
        new_text = conn.execute(text("SELECT contract_text FROM coachee WHERE id=:c"), {"c": cid}).scalar()
        history = conn.execute(
            text("SELECT contract_text FROM contract_history WHERE coachee_id=:c"), {"c": cid}
        ).fetchall()
    assert new_text == "brand new contract text"
    assert any(h[0] == "old text" for h in history)


def test_checked_sample_tasks_create_task_templates_unchecked_do_not(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    engine = get_engine()
    with engine.connect() as conn:
        section_id = conn.execute(text("SELECT section_id FROM contract_section_task LIMIT 1")).scalar()
        task_id = conn.execute(
            text("SELECT id, title FROM contract_section_task WHERE section_id=:s LIMIT 1"), {"s": section_id}
        ).fetchone()
        other_task = conn.execute(
            text("SELECT id FROM contract_section_task WHERE section_id=:s AND id != :t"),
            {"s": section_id, "t": task_id[0]},
        ).fetchone()

    client.post(
        f"/coach/coachee/{cid}/contract/draft",
        data={"action": "save", "assembled_text": "text", "task_ids": [str(task_id[0])]},
    )

    with engine.connect() as conn:
        created = conn.execute(
            text("SELECT 1 FROM task_template WHERE coach_id=1 AND title=:t"), {"t": task_id[1]}
        ).fetchone()
        count = conn.execute(text("SELECT COUNT(*) FROM task_template WHERE coach_id=1")).scalar()
    assert created is not None
    assert count == 1  # the unchecked other_task (and any others) were not created
    assert other_task is not None  # sanity: there really was another task not checked


def test_deleting_coach_cleans_up_private_section_tasks(client):
    """contract_section_task has no coach_id/coachee_id column of its own - it hangs
    off contract_section.id one hop further out, invisible to the generic
    coach_id/coachee_id-column cascade scan. Without routes_admin.py's explicit
    cleanup, this would FK-violate (Postgres) or silently orphan (SQLite) on
    delete. Covers the same bug class as BUG-017, one hop further out.
    """
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    client.post(
        "/admin/coach/add",
        data={"username": "victimcoach", "password": "pass123", "name": "Victim Coach", "timezone": "UTC"},
    )
    client.get("/logout")
    client.post("/login", data={"username": "victimcoach", "password": "pass123"})
    client.post("/coach/contract-sections", data={"action": "create", "title": "Victim Section", "body": "x"})
    engine = get_engine()
    with engine.connect() as conn:
        victim_coach_id = conn.execute(text("SELECT id FROM coach WHERE username='victimcoach'")).scalar()
        section_id = conn.execute(text("SELECT id FROM contract_section WHERE title='Victim Section'")).scalar()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO contract_section_task (section_id, title) VALUES (:s, 'Victim Task')"),
            {"s": section_id},
        )
    client.get("/logout")

    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    resp = client.post(f"/admin/coach/{victim_coach_id}/delete")
    assert resp.status_code == 302

    with engine.connect() as conn:
        left_section = conn.execute(text("SELECT 1 FROM contract_section WHERE id=:s"), {"s": section_id}).fetchone()
        left_task = conn.execute(
            text("SELECT 1 FROM contract_section_task WHERE section_id=:s"), {"s": section_id}
        ).fetchone()
    assert left_section is None
    assert left_task is None


def test_non_owning_coach_cannot_draft_for_anothers_coachee(client):
    client.post("/login", data={"username": "ecb", "password": "ecbF3T"})
    cid = _add_coachee(client)
    client.post(
        "/admin/coach/add",
        data={"username": "othercoach7", "password": "pass123", "name": "Other Coach 7", "timezone": "UTC"},
    )
    client.get("/logout")

    client.post("/login", data={"username": "othercoach7", "password": "pass123"})
    resp = client.get(f"/coach/coachee/{cid}/contract/draft")
    assert resp.status_code == 404
