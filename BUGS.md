# BUGS.md — Known Defects (DSCoaching)

## Legend

| Severity | Meaning |
|----------|---------|
| **critical** | Causes runtime errors or data corruption in production |
| **medium** | Incorrect behavior but doesn't crash; user-facing annoyance |
| **low** | Code smell, minor UX issue, or future-proofing concern |

---

## Active Bugs

| ID | Severity | Description | Location | Status | Notes |
|----|----------|-------------|----------|--------|-------|
| BUG-001 | critical | `ORDER BY RANDOM()` is PostgreSQL syntax; MySQL requires `ORDER BY RAND()` | `src/app.py` line 123 (`_auto_assign_reserves`) | **fixed** | Reserve task assignment would fail with SQL error on MySQL. Fixed in Task 1. |
| BUG-002 | medium | `IF(status='active','frozen','active')` is MySQL-only; PostgreSQL requires `CASE WHEN` | `src/app.py` line 1299 (`admin_freeze_coach`) | **fixed** | Replaced with portable `CASE WHEN ... END` in Task 2. |
| BUG-003 | medium | `ON DUPLICATE KEY UPDATE` is MySQL-only; PostgreSQL requires `ON CONFLICT DO UPDATE` | `src/app.py` line 634 (`save_profile`) | **fixed** | Replaced with select-then-insert/update pattern in Task 2. |
| BUG-004 | medium | `INTERVAL 90 DAY` / `INTERVAL 7 DAY` — MySQL syntax; PG uses `INTERVAL '90 days'` | `src/app.py` lines 1224, 1272, 1276 | **fixed** | Replaced with Python date arithmetic in Task 2. |
| BUG-005 | low | `_audit()` silently swallows all exceptions with bare `except Exception: pass` | `src/helpers.py::_audit` | **fixed** | Added `print(f"[_audit] write failed for action={action!r}: {e}")` - still never raises (auditing must not break a request), but no longer invisible. `tests/test_h3_logging.py` covers it. |
| BUG-006 | low | `admin_delete_coach` uses bare `except Exception: pass` for cascade deletions | `src/routes_admin.py` | **resolved by BUG-017** | The metadata-driven cascade rewrite (BUG-017) replaced the per-table try/except entirely - deletes now run directly and a real failure propagates rather than being caught. No separate action needed. |
| BUG-007 | low | `forgotPw()` in login template hardcodes `papillon.severin@gmail.com` | `src/templates/login.html` line 33 | **fixed** | Replaced with `SUPPORT_EMAIL` env var (`helpers.py`, same pattern as `ATTACHMENTS_DIR`), injected into every template via `inject_helpers()`. Link and `mailto:` are omitted entirely from the login page when unset (the default), so no address ships unconfigured. `tests/test_forgot_password.py`. |
| BUG-008 | low | No HTTP error handlers (404, 500, 403) — errors return bare strings | `src/app.py` (missing) | **fixed** | Added styled error handlers in Task 9. |
| BUG-009 | low | `coach_brand = c.fetchone()` could return `None` if coach deleted mid-session | `src/app.py` line 265 (login flow) | open | Race condition: coachee logs in, coach is deleted between queries. |
| BUG-010 | low | No input length validation — form values could exceed VARCHAR column limits | Various routes | open | Truncation or DB error on oversized input. |
| BUG-011 | low | `_auto_assign_reserves` runs on every coachee dashboard load (N+1 queries) | `src/app.py` line 82 | open | Performance concern at scale; acceptable for personal use. |
| BUG-012 | low | `c.lastrowid` is pymysql-specific; not available on psycopg2 | `src/app.py` lines 320, 700 | **fixed** | Handled by _SAConn wrapper with fallback to inserted_primary_key. |
| BUG-013 | low | No CSRF protection on any form | `src/app.py` (all POST routes) | **fixed** | Token-based CSRF added in `src/csrf.py`; `{{ csrf_field() }}` renders `_csrf_token` hidden input in all forms. |
| BUG-014 | low | `elif True:` on line 112 — always assigns recurring task on first encounter; dead branch logic | `src/app.py` line 112 | **fixed** | Changed to `else:` — functionally equivalent, now reads correctly. |
| BUG-015 | low | `init_db()` on app startup wrapped in bare try/except — masks schema migration failures | `src/app.py::create_app` | **not actually a live bug** | Current code already does `print(f"DB init warning: {e}")` on failure - not silent. Re-verified while doing the H3 pass; closing as already-fine rather than re-fixing. |
| BUG-016 | low | `GREATEST(best_streak, current_streak+1)` — not supported on SQLite | `src/app.py` line 160 | **fixed** | Replaced with portable CASE WHEN expression in Task 2. |
| BUG-017 | **high** | `admin_delete_coach` cascade did not clean 10+ newer tables (badge, ritual, ritual_log, auto_rule, week_plan, onboarding_step, payment_plan, payment_log, creative_collection, creative_constraint, creative_work) → FK violation on `DELETE FROM coachee`/`coach` → **HTTP 500 on `/admin/coach/<id>/delete` in production**. | `src/routes_admin.py` (`admin_delete_coach`) | **fixed** | Rewrote cascade to derive the table list from the SQLAlchemy `metadata` FK graph (reverse topological order), so every coach/coachee-referencing table — including future ones like `score_log` — is covered automatically. Added generic metadata-driven orphan test (`test_delete_coach_leaves_zero_orphans_in_every_table`) that seeds + checks every referencing table; verified it fails against the old handler and passes against the fix. |
| BUG-018 | **high** | `{{ csrf_field() }}` rendered **outside** `<form>` in 7 places → token not submitted → POST rejected (403) with server-side CSRF enforcement. Affected the coachee **safe-word / STOP** buttons (`coachee_dashboard.html`), the pin-note (`coach_view_coachee.html`), delete-step (`onboarding.html`), delete-plan (`week_plan.html`), deactivate-plan (`payments.html`), and dashboard nudge/quick-pay (`coach_dashboard.html`). | 7 templates | **fixed** | Found by reviewer (H10) + 2 more found by the new generic test. Moved csrf_field inside each `<form>`. Regression test `tests/test_csrf_placement.py` scans all templates generically (immune to new templates). |
| BUG-019 | medium | Secrets exposed in client-side JS: `llm_key` and `tg_token` (Telegram bot token) embedded via `|tojson` in `coach_view_coachee.html` (lines ~368/410/414); Telegram Bot API called directly from the browser with the token. Visible in page source to anyone who can view the page. | `src/templates/coach_view_coachee.html` | **fixed** | Reviewer H11. `llm_key` was dead code (never read client-side) — deleted. Telegram send moved to a new server-side proxy route (`POST /coach/coachee/<cid>/telegram-notify`); the bot token never reaches the browser now. Regression test `tests/test_telegram_notify.py` asserts the token never appears in rendered HTML and that the server-side call carries it. |
| BUG-020 | medium | IDOR: `generate_profile`, `save_profile`, and the profile-prompt-preview route took `cid` from the URL but never verified the coachee belongs to the logged-in coach — any logged-in coach could read/trigger AI generation for another coach's coachee by guessing/incrementing the id. (`ai-digest` and `conditioning/generate` already had the correct check on closer inspection — only these 3 were actually missing it.) | `src/routes_coach.py` (`get_profile_prompt`, `generate_profile`, `save_profile`) | **fixed** | Added the same `WHERE id=%s AND coach_id=%s` ownership check already used correctly by `ai_weekly_digest`/`generate_conditioning`/`excuse_task`/`telegram_notify`. `tests/test_idor_ai_profile.py` covers all 3 routes rejecting a non-owning coach (404) and confirms the owning coach still works. |
| BUG-021 | medium | `edit_coachee` (the main coachee-settings form handler) replaces `coachee.features` wholesale with just the fixed feature-flag booleans, instead of merging — silently wipes any other key stored there on every save. Already affected `photo_validation_pct` (pre-existing, undetected) and would have broken R49's new `week_start` preference on the very next settings save. | `src/routes_coach.py::edit_coachee` | **fixed** | Found while wiring up R49's week-boundary preference. Changed to read-merge-write. `tests/test_scoring.py::test_editing_coachee_settings_preserves_week_start_preference` guards against regression. |
| BUG-022 | low | `_mood_sparkline` silently swallows all query exceptions, returning `[]` with no trace — same H3 class as BUG-005. | `src/automation.py::_mood_sparkline` | **fixed** | Added a print on failure, same pattern as BUG-005's fix. Still returns `[]` (non-blocking for the dashboard widget) but now visible. `tests/test_h3_logging.py`. |
| BUG-023 | low | AI photo-validation failures in `complete_task` are silently swallowed (`except Exception: pass`) — correct to stay non-blocking (a 3rd-party AI outage shouldn't block task submission) but invisible, same H3 class. | `src/routes_coachee.py::complete_task` | **fixed** | Added a print on failure; submission still succeeds either way. `tests/test_h3_logging.py`. |

---

## Resolved

| ID | Fixed In | Description |
|----|----------|-------------|
| BUG-001 | Task 1 | `ORDER BY RANDOM()` → `ORDER BY RAND()` (now dialect-aware via `_rand_func()`) |
| BUG-002 | Task 2 | `IF()` → `CASE WHEN ... END` |
| BUG-003 | Task 2 | `ON DUPLICATE KEY UPDATE` → select-then-insert/update |
| BUG-004 | Task 2 | `INTERVAL N DAY` → Python date arithmetic |
| BUG-008 | Task 9 | Added @app.errorhandler for 404/403/500 with styled template |
| BUG-012 | Task 2 | `c.lastrowid` → `_SAConn.lastrowid` wrapper |
| BUG-014 | Task 1 | `elif True:` → `else:` (dead branch cleanup) |
| BUG-016 | Task 2 | `GREATEST()` → `CASE WHEN` for SQLite compat |
| BUG-018 | this PR | `csrf_field()` moved inside `<form>` in 7 templates (incl. safe-word buttons); generic regression test added |
| BUG-017 | this PR | metadata-driven cascade in `admin_delete_coach` (fixes prod 500 on coach delete); generic zero-orphan regression test added |
| BUG-007 | this PR | hardcoded forgot-password address → `SUPPORT_EMAIL` env var, link hidden when unset |
