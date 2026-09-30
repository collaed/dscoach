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
| BUG-005 | low | `_audit()` silently swallows all exceptions with bare `except Exception: pass` | `src/app.py` line 29 | open | Audit failures are invisible; at minimum should log to stderr. |
| BUG-006 | low | `admin_delete_coach` uses bare `except Exception: pass` for cascade deletions | `src/app.py` lines 1321, 1327 | open | Acceptable for cascade cleanup, but should log failures. |
| BUG-007 | low | `forgotPw()` in login template hardcodes `papillon.severin@gmail.com` | `src/templates/login.html` line 33 | open | Should be configurable per-deployment or removed. |
| BUG-008 | low | No HTTP error handlers (404, 500, 403) — errors return bare strings | `src/app.py` (missing) | **fixed** | Added styled error handlers in Task 9. |
| BUG-009 | low | `coach_brand = c.fetchone()` could return `None` if coach deleted mid-session | `src/app.py` line 265 (login flow) | open | Race condition: coachee logs in, coach is deleted between queries. |
| BUG-010 | low | No input length validation — form values could exceed VARCHAR column limits | Various routes | open | Truncation or DB error on oversized input. |
| BUG-011 | low | `_auto_assign_reserves` runs on every coachee dashboard load (N+1 queries) | `src/app.py` line 82 | open | Performance concern at scale; acceptable for personal use. |
| BUG-012 | low | `c.lastrowid` is pymysql-specific; not available on psycopg2 | `src/app.py` lines 320, 700 | **fixed** | Handled by _SAConn wrapper with fallback to inserted_primary_key. |
| BUG-013 | low | No CSRF protection on any form | `src/app.py` (all POST routes) | **fixed** | Token-based CSRF added in `src/csrf.py`; `{{ csrf_field() }}` renders `_csrf_token` hidden input in all forms. |
| BUG-014 | low | `elif True:` on line 112 — always assigns recurring task on first encounter; dead branch logic | `src/app.py` line 112 | **fixed** | Changed to `else:` — functionally equivalent, now reads correctly. |
| BUG-015 | low | `init_db()` on app startup wrapped in bare try/except — masks schema migration failures | `src/app.py` line 1368 | open | At least prints error, but could hide critical schema issues. |
| BUG-016 | low | `GREATEST(best_streak, current_streak+1)` — not supported on SQLite | `src/app.py` line 160 | **fixed** | Replaced with portable CASE WHEN expression in Task 2. |
| BUG-017 | medium | `admin_delete_coach` cascade does not clean 11 newer tables (badge, ritual, ritual_log, auto_rule, week_plan, onboarding_step, payment_plan, payment_log, creative_collection, creative_constraint, creative_work) | `src/routes_admin.py` (`admin_delete_coach`) | open | Deleting a coach leaves orphaned rows in these tables. Add them to the cascade lists (coachee-level and coach-level). |

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
