# data-model.md — Database Schema (36 tables, SQLAlchemy Core)

## Schema Management

All schema lives in `src/models.py` as SQLAlchemy Core `Table()` definitions. Schema creation is handled by `metadata.create_all(engine)` in `database.py → init_db()`. This is idempotent — safe to call on every startup.

`init_db()` also seeds accounts via `_seed_admin()` and `_seed_demo_users()`:

| Username | Password | Role | Notes |
|----------|----------|------|-------|
| `ecb` | `ecbF3T` | Admin + Coach | Created/updated on every startup |
| `Kitsune` | `Goddess` | Coach | Demo coach account |
| `severin` | `ecbS3V` | Coachee | Linked to Kitsune |

Password storage: `sha256(plaintext.encode()).hexdigest()` — no salt (historical; migration to argon2id planned in Phase 2).

**Legacy files:** `src/db.py` (MySQL raw DDL) and `src/db_pg.py` (PG raw DDL) are kept for reference but unused. The app imports only from `database` and `models`.

**Migration strategy:** SQLAlchemy's `create_all()` only creates missing tables — it won't ALTER existing ones. For column additions on production, either:
1. Add the column manually via `psql` on ecb.pm before deploy
2. Or use a one-off migration script

## Portable Types

No ENUMs (not portable across dialects). Status fields use `String(20)` with application-level validation.

| SQLAlchemy Type | MySQL | PostgreSQL | SQLite |
|----------------|-------|------------|--------|
| `Integer` | INT | INTEGER | INTEGER |
| `String(N)` | VARCHAR(N) | VARCHAR(N) | TEXT (no enforcement) |
| `Text` | TEXT | TEXT | TEXT |
| `DateTime` | DATETIME | TIMESTAMP | TEXT |
| `Date` | DATE | DATE | TEXT |
| `Time` | TIME | TIME | TEXT |
| `SmallInteger` | SMALLINT | SMALLINT | INTEGER |
| `JSON` | JSON | JSON | TEXT |

## Entity Relationships

```mermaid
erDiagram
    COACH ||--o{ COACHEE : "manages"
    COACH ||--o{ TASK_TEMPLATE : "creates"
    COACHEE ||--o{ TASK_ASSIGNMENT : "receives"
    TASK_TEMPLATE ||--o{ TASK_ASSIGNMENT : "instantiates"
    COACHEE ||--o{ CHECKIN : "submits"
    COACHEE ||--o{ TRACKING_LOG : "logs"
    COACHEE ||--o{ NOTE : "exchanges"
    COACH ||--o{ ACKNOWLEDGEMENT : "gives"
    COACHEE ||--o{ ACKNOWLEDGEMENT : "receives"
    COACH ||--o{ MENTAL_CONDITIONING : "creates"
    COACHEE ||--o{ MENTAL_CONDITIONING_RESPONSE : "answers"
    COACHEE ||--o{ GOAL : "proposes"
    COACHEE ||--o{ JOURNAL : "writes"
    COACHEE ||--o{ PROGRESS_PHOTO : "uploads"
    COACHEE ||--o{ VOICE_NOTE : "records"
    COACHEE ||--|| PSYCHOLOGICAL_PROFILE : "has"
```

## Tables

### coach

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| username | String(100) UNIQUE | Login identifier |
| password_hash | String(255) | sha256 hex digest |
| name | String(200) | Display name |
| timezone | String(64) | Default 'Europe/London' |
| logo_path | String(500) | Path to uploaded logo file |
| accent_color | String(20) | UI branding, default '#e94560' |
| bg_color | String(20) | UI branding, default '#1a1a2e' |
| card_color | String(20) | UI branding, default '#16213e' |
| telegram_bot_token | String(200) | For Telegram notifications |
| is_admin | SmallInteger | 0 or 1 |
| status | String(20) | 'active' or 'frozen' |
| email | String(200) | Contact email |
| features | JSON | Feature flag overrides |
| created_at | DateTime | Auto-set |

### coachee

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| username | String(100) UNIQUE | Login identifier |
| password_hash | String(255) | sha256 hex digest |
| name | String(200) | Display name |
| coach_id | Integer FK→coach | Which coach owns this coachee |
| contract_text | Text | Current active contract |
| safe_word | String(100) | Default 'RED' — triggers full stop |
| status | String(20) | 'active', 'paused', or 'stopped' |
| task_unveil_time | Time | When tasks become visible (default 08:00) |
| task_freeze_time | Time | When tasks auto-miss (default 22:00) |
| timezone | String(64) | For correct date handling |
| context_text | Text | Coach's private notes about coachee |
| strikes | Integer | Accumulated strikes |
| avatar | String(50) | Emoji avatar (default '🐕') |
| color_scheme | String(20) | UI accent color |
| telegram_chat_id | String(100) | For push notifications |
| features | JSON | Per-coachee feature overrides |
| current_streak | Integer | Consecutive completion days |
| best_streak | Integer | All-time best streak |
| last_streak_date | Date | Last date streak was updated |
| login_count | Integer | For onboarding banner (shows first 3 logins) |
| created_at | DateTime | Auto-set |

### task_template

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| coach_id | Integer FK→coach | |
| title | String(300) | |
| description | Text | |
| recurrence | String(20) | 'once', 'daily', 'weekly' |
| category | String(20) | 'mental', 'physical', 'emotional', 'admin' |
| difficulty | String(20) | 'easy', 'medium', 'hard' |
| is_reserve | SmallInteger | Auto-assigned when no manual task |
| recur_days | Integer | Recurs every N days |
| recur_approx | SmallInteger | Fuzzy recurrence (±25% randomization) |
| in_library | SmallInteger | Appears in task library search |
| created_at | DateTime | |

### task_assignment

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| template_id | Integer FK→task_template | |
| coachee_id | Integer FK→coachee | |
| due_date | Date | |
| status | String(20) | 'pending', 'completed', 'partial', 'missed', 'excused' |
| visible_after | DateTime | Task becomes visible at this time |
| frozen_after | DateTime | Task auto-misses after this time |
| response | Text | Coachee's completion response |
| responded_at | DateTime | When coachee submitted |
| grade | String(1) | A-F from coach |
| coach_comment | Text | Feedback |
| attachment_path | String(500) | Photo attachment |
| reflection_rating | SmallInteger | 1-5 self-assessment |
| reflection_text | Text | Self-reflection |
| depends_on | Integer | Task ID that must complete first |
| created_at | DateTime | |

### checkin, tracking_log, note, acknowledgement, mental_conditioning, mental_conditioning_response, psychological_profile, contract_history, audit_log, weekly_summary, voice_note, goal, journal, progress_photo, support_message

All follow the same pattern: Integer PK, coachee_id FK, content fields, created_at. See `src/models.py` for exact definitions.

## Planned schema additions — R48 / R49 (see `plan-proof-and-scoring.md`)

Not yet implemented; documented here for the review of the planning batch.

**`task_template`** (new columns):

| Column | Type | Notes |
|--------|------|-------|
| proof_pct | SmallInteger | Default 0. 0–100 chance an occurrence demands photo proof (R48). |
| points | SmallInteger | Default 0. Signed score value awarded on completion / deducted on miss (R49). |

**`task_assignment`** (new column):

| Column | Type | Notes |
|--------|------|-------|
| proof_required | SmallInteger | Default 0. Rolled once at assignment from the template's `proof_pct` and persisted (never re-rolled on display). When 1, completion without a photo is rejected (R48). |

**`score_log`** (new table, append-only ledger):

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | NOT NULL |
| points | SmallInteger | Signed delta |
| reason | String(40) | 'task_completed' \| 'task_missed' \| 'proof_bonus' \| 'miss_reversed' \| 'manual' \| 'checkin' \| 'reward_redeemed' |
| task_assignment_id | Integer FK task_assignment.id | Nullable |
| score_date | Date | Coachee-local date (not server UTC) |
| note | String(200) | Nullable |
| created_at | DateTime | Auto-set |
| — | UniqueConstraint(task_assignment_id, reason) | Idempotency. NULL assignment ids do not collide (standard SQL), so multiple manual/checkin awards coexist. |

Index: `ix_score_log_coachee_date` on `(coachee_id, score_date)` for rollups.

Migration: Alembic `003_proof_and_scoring` (`batch_alter_table` for SQLite).

**`coachee`** (new column, R42): `protocol_mode` String(20), default `'relaxed'` — `'relaxed' | 'formal'`.

**`note`** (new column, R42): `tagged_mode` String(20), nullable — the coachee's `protocol_mode`
at submission time, stamped only on coachee-authored notes.

**`protocol_mode_log`** (new table, append-only, R42):

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | NOT NULL |
| mode | String(20) | 'relaxed' \| 'formal' |
| changed_by_coach_id | Integer FK coach.id | NOT NULL |
| created_at | DateTime | Auto-set |

Migration: Alembic `006_r42_protocol_mode` (`batch_alter_table` for SQLite).

**`coachee`** (3 new columns, R47): `unavailable_since` (DateTime, nullable - set when a
declaration is active), `unavailable_until` (Date, nullable - NULL means indefinite),
`unavailable_note` (String(300), nullable). Ending an unavailability clears all three; an expired
`unavailable_until` is detected by comparison in `tasks._is_unavailable()`, no sweep needed.

Migration: Alembic `007_r47_unavailability` (`batch_alter_table` for SQLite).

**`coachee`** (new column, R40): `checkin_mode` String(20), default `'optional'` —
`'optional' | 'rewarded' | 'required'`. Bonus/penalty amounts are configurable via the existing
`coach.features` JSON column (`checkin_bonus`, `checkin_miss_penalty` keys), same storage pattern
as `proof_bonus`/`week_start` — no new columns needed for those. `score_log` gains two more
`reason` values: `'checkin'` (rewarded bonus, one row per check-in submission) and
`'checkin_missed'` (required-mode penalty, at most one row per coachee per missed calendar day).

Migration: Alembic `008_r40_checkin_mode` (`batch_alter_table` for SQLite).

**`reward_catalog`** (new table, R24): coach-defined, point-priced rewards.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | NOT NULL |
| title | String(200) | NOT NULL |
| description | String(500) | Nullable |
| point_cost | SmallInteger | NOT NULL |
| active | SmallInteger | Default 1; deactivated rewards are hidden from the coachee, never hard-deleted |
| created_at | DateTime | Auto-set |

**`reward_redemption`** (new table, R24/R51): a coachee's request against the catalog above.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | NOT NULL |
| reward_catalog_id | Integer FK reward_catalog.id | NOT NULL |
| point_cost | SmallInteger | Snapshot at request time (survives a later catalog price change) |
| status | String(20) | 'pending' \| 'approved' \| 'denied' |
| requested_at | DateTime | Auto-set |
| decided_at | DateTime | Nullable |
| decided_by_coach_id | Integer FK coach.id | Nullable |

Approval appends a negative `score_log` row (`reason='reward_redeemed'`) - the R49 running
score **is** the balance (`score_summary(...)["all_time"]`), there is no separate counter.
Requesting never spends anything by itself; only an approval does, and only if the balance is
still sufficient at that moment (re-checked, since it may have changed since the request).

Migration: Alembic `009_r24_r51_rewards` (plain `create_table`, no existing-table changes).

**`contract_section`** (new table, R52): a reusable contract clause. `coach_id` NULL means a
system default (shared, read-only, cloneable); non-NULL means private to that coach.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | **Nullable** - NULL = system default. The only nullable `coach_id` in the schema; see BUG-024 for the cascade-delete implication. |
| title | String(200) | NOT NULL |
| category | String(40) | 'foundation'\|'roles'\|'consent'\|'time'\|'ritual'\|'service'\|'rewards'\|'physical'\|'evaluation'\|'dissolution'\|'custom' |
| body | Text | NOT NULL; may contain `{{coach_name}}`/`{{name}}`/other `merge.py` vars |
| reusability | String(20) | 'reusable_boilerplate'\|'adapt_heavily'\|'custom' - `adapt_heavily` renders a warning wherever shown |
| sort_hint | SmallInteger | Default library order |
| active | SmallInteger | Default 1 |
| created_at | DateTime | Auto-set |

**`contract_section_task`** (new table, R52): a sample task offered (never forced) when a
section is included in a drafted contract.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| section_id | Integer FK contract_section.id | NOT NULL - one section per task (the source data's few multi-section tasks keep only their first link) |
| title | String(300) | NOT NULL |
| description | Text | May contain merge vars |
| category / difficulty / recurrence / recur_days / is_reserve / tags | — | Same shape as `task_template`, copied into a real `task_template` row only if the coach checks this task when saving a draft |
| proof_pct | SmallInteger | R48 |
| points | SmallInteger | R49 |
| created_at | DateTime | Auto-set |

Seeded once (idempotent) by `database.py::_seed_contract_library()` from
`src/seed_data/contract_library_seed.json` - 20 sections, 23 tasks, genericized from a real
contract. `coachee.contract_text`/`contract_history` are unchanged by this feature (REQ-52.5):
drafting just produces the same free text through a scaffold, not a new storage mechanism.

Migration: Alembic `010_r52_contract_sections` (plain `create_table`, no existing-table changes).

**`weekly_summary`** (new column, R43): `designation` String(10), nullable — `'green' | 'yellow' | 'red'`,
coach-assigned per calendar week (Monday-aligned, same convention as the existing weekly-stats
route). Not every week gets one.

Migration: Alembic `011_r43_weekly_designation` (`batch_alter_table` for SQLite).

## Cascade Delete Order

> ⚠️ **BUG-017 / H1 (open):** the cascade below does **not** include the 11
> "Extended Tables" (`badge`, `ritual`, `ritual_log`, `auto_rule`, `week_plan`,
> `onboarding_step`, `payment_plan`, `payment_log`, `creative_collection`,
> `creative_constraint`, `creative_work`) — deleting a coach orphans their rows.
> Recommended fix: derive the cascade from `metadata` FK graph so new tables
> (including `score_log`) are covered automatically. See `backlog.md` H1.


When a coach is deleted (`admin_delete_coach`), cleanup happens in this order:
1. For each coachee: delete from checkin, tracking_log, note, acknowledgement, mental_conditioning_response, task_assignment, psychological_profile, contract_history, goal, journal, voice_note, progress_photo, weekly_summary
2. Delete from coachee
3. Delete from task_template, mental_conditioning (coach-level)
4. Delete from coach

This is tested in `tests/test_admin_delete.py` — verifies all 14 tables emptied, no FK violations.

## Extended Tables (gamification, rituals, automation, scheduling, payments, creative archive)

These 11 tables were added after the initial 19 and support later features.

### badge

Gamification awards earned by a coachee.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | Owner |
| badge_type | String(50) | Category of badge |
| badge_name | String(200) | Display name |
| description | String(500) | What it was earned for |
| icon | String(50) | Emoji or icon key |
| created_at | DateTime | Awarded timestamp |

### ritual

Recurring ritual definitions (shared or per-coachee).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | Author |
| coachee_id | Integer FK coachee.id | NULL = shared with all coachees |
| name | String(200) | Ritual name |
| description | Text | Instructions |
| schedule | String(50) | Default 'daily' |
| schedule_days | String(50) | Specific days if not daily |
| active | SmallInteger | 0 or 1 |
| created_at | DateTime | Auto-set |

### ritual_log

Completion records for rituals. Unique on `(ritual_id, coachee_id, completed_date)` for idempotency.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| ritual_id | Integer FK ritual.id | Which ritual |
| coachee_id | Integer FK coachee.id | Who completed it |
| completed_date | Date | Day of completion |
| created_at | DateTime | Auto-set |

### auto_rule

Coach-defined automation rules (trigger → condition → action).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | Owner |
| name | String(200) | Rule name |
| trigger | String(50) | Event that fires the rule |
| condition_field | String(50) | Field to test |
| condition_op | String(10) | Comparison operator |
| condition_value | String(100) | Value to compare against |
| action_type | String(50) | What to do |
| action_template | Text | Action payload (mail-merge template) |
| active | SmallInteger | 0 or 1 |
| created_at | DateTime | Auto-set |

### week_plan

Weekly recurring task schedule (day-of-week → template).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | Owner |
| day_of_week | SmallInteger | 0-6 |
| template_id | Integer FK task_template.id | Task to assign |
| coachee_id | Integer FK coachee.id | NULL = all coachees |
| created_at | DateTime | Auto-set |

### onboarding_step

Scripted onboarding sequence (day offset → template or note).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | Owner |
| day_offset | SmallInteger | Days after coachee creation |
| template_id | Integer FK task_template.id | Optional task to assign |
| note_text | Text | Optional welcome note |
| created_at | DateTime | Auto-set |

### payment_plan

Recurring payment configuration per coachee. Unique on `coachee_id` (one plan each).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id UNIQUE | One plan per coachee |
| frequency | String(20) | e.g. monthly |
| amount | String(50) | Amount as string |
| currency | String(10) | Default 'EUR' |
| start_date | Date | Plan start |
| active | SmallInteger | 0 or 1 |
| created_at | DateTime | Auto-set |

### payment_log

Confirmed payment records.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | Payer |
| amount | String(50) | Amount as string |
| currency | String(10) | Default 'EUR' |
| period_start | Date | Billing period start |
| period_end | Date | Billing period end |
| confirmed_at | DateTime | When confirmed |
| notes | String(500) | Optional |
| created_at | DateTime | Auto-set |

### creative_collection

A themed collection of creative works by a coachee.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | Author |
| title | String(300) | Collection title |
| description | Text | Optional |
| status | String(20) | Default 'active' |
| created_at | DateTime | Auto-set |

### creative_constraint

A creative prompt/constraint assigned by the coach.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coach_id | Integer FK coach.id | Author |
| coachee_id | Integer FK coachee.id | Target |
| constraint_type | String(30) | Kind of constraint |
| constraint_value | Text | The constraint content |
| active_date | Date | When it applies |
| used | SmallInteger | 0 or 1 |
| created_at | DateTime | Auto-set |

### creative_work

A single creative work (poem, prose, etc.), optionally tied to a collection and constraint.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| coachee_id | Integer FK coachee.id | Author |
| collection_id | Integer FK creative_collection.id | Optional grouping |
| constraint_id | Integer FK creative_constraint.id | Prompt that inspired it |
| title | String(300) | Optional |
| content | Text | The work itself |
| work_type | String(30) | Default 'poem' |
| tags | String(500) | Comma-separated |
| coach_notes | Text | Coach feedback |
| selected_for_final | SmallInteger | 0 or 1 |
| created_at | DateTime | Auto-set |

> Note: the cascade-delete routine in `admin_delete_coach` predates these 11 tables and does not yet clean all of them. Tracked as future work; see BUGS.md.
