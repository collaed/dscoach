# backlog.md — Prioritized Backlog

Living, prioritized view distilled from `roadmap.md` (R1–R51) and the
2026-09-30 planning batch. The roadmap is the exhaustive catalogue with
implementation notes; this file is the *ordered work queue* — what to pick up
next and why. Status mirrors the roadmap (🟢 done · 🟡 partial · 🔴 not started).

## Now (this planning batch — 2026-09-30)

| Item | What | Why now | Ref |
|------|------|---------|-----|
| Commit refactor | Land the large uncommitted modular refactor as its own commit (81 tests green) | Keeps the feature diffs reviewable; unversioned work is a risk | project.md |
| R48 | ✅ **Done** — probabilistic proof demand, all 5 assignment sites + completion enforcement + UI disclosure | Directly requested; low schema cost; big workload/UX win on recurring tasks | plan-proof-and-scoring.md |
| R49 | ✅ **Done** — points, score_log ledger, rollups, excuse-reverses-penalty, week_start preference | Directly requested; self-contained; foundational for R24/R51 | plan-proof-and-scoring.md |
| R50 | ✅ **Done** — noir theme, toggles on both settings screens, branding preset | Directly requested; opt-in, additive, low risk | plan-aesthetic-noir.md |
| H1 / BUG-017 | ✅ **Done** — metadata-driven cascade (walks the FK graph), generic zero-orphans test | Data-integrity bug; worsens as more coach-scoped tables ship (incl. `score_log`) | BUGS.md |
| H8 | ✅ **Done** — fixed stale `models.py` table-count docstring | 30 tables; trivial | models.py |
| H10 / BUG-018 | ✅ **Done in this PR** — `csrf_field()` moved inside `<form>` in 7 templates (incl. safe-word); generic regression test added | Safety-critical: safe-word/STOP button was CSRF-rejected | BUGS.md |
| H11 / BUG-019 | ✅ **Done** — dead `llm_key` deleted; Telegram send moved to a server-side proxy route (`/coach/coachee/<cid>/telegram-notify`); regression test asserts the token never reaches rendered HTML | Secrets exposed in page source | BUGS.md |
| BUG-020 | ✅ **Done** — ownership check added to the 3 routes that actually lacked it (`ai-digest`/`conditioning/generate` already had it) | Any coach can read/trigger generation for another coach's coachee | BUGS.md |

## Next (quick wins, low risk)

| Item | What | Ref |
|------|------|-----|
| H3 | ✅ **Done** — `_audit`/`_mood_sparkline`/photo-validation now print on failure; cascade (006) resolved by BUG-017's rewrite; `init_db` (015) was already non-silent on inspection | BUG-005/006/015, +022/023 found in the same pass |
| H4 | ✅ **Done** — hardcoded email replaced with `SUPPORT_EMAIL` env var; link hidden when unset | BUG-007 |
| H7 | ✅ **Done** — guarded `None` coach in login flow; also fixed error-message fallthrough bug found along the way | BUG-009 |
| H5 | ✅ **Done** — shared length-validation helper wired into register + add_coachee (the two unvalidated account-creation paths) | BUG-010 |
| R26 | ✅ **Done** — idle timeout (default 30 min, `SESSION_TIMEOUT_MINUTES`), HSTS + no-store on every response, `Clear-Site-Data` on logout | roadmap R26 |
| R42 | ✅ **Done** — `protocol_mode` on coachee, coach toggle + mode-history log, dashboard badge, coachee-note tagging | roadmap R42 |
| R47 | ✅ **Done** — `unavailable_since/until/note` on coachee, self + coach declare/end, pauses auto-assign + freeze-overdue | roadmap R47 |
| R40 | Check-in modes (optional/rewarded/required) — "rewarded" ties into R49 | roadmap R40 |

## Soon (high impact, moderate effort)

| Item | What | Ref |
|------|------|-----|
| R51 | Make R24 rewards spend the R49 score | roadmap R51 |
| R52 | Section-based contract drafting (clause library + sample-task association) | plan-contract-drafting.md |
| R6 → H2 | LLM auto-rating to replace the gameable length-based auto-grade | roadmap R6, H2 |
| R1 → R4 → R5 | Late check-in marking → compliance dashboard → timeliness | roadmap R1/R4/R5 |
| R18 | Automatic ritual-miss detection | roadmap R18 |
| R38 → R39 | Ritual categories/scheduling depth → completion calendar | roadmap R38/R39 |
| R43 | Weekly status designation (GREEN/YELLOW/RED) | roadmap R43 |
| R15 → R17 → R27 | Timed consequences → auto-triggers → graduated ladder | roadmap R15/R17/R27 |

## New modules (larger, self-contained)

| Item | What | Ref |
|------|------|-----|
| R32 / H9 | Video proof (MediaRecorder, 30 MB webm, multipart) — enables richer R48 proofs | roadmap R32 |
| R31 → R32 → R33 | Position/posture library → position rituals → command vocabulary | roadmap R31–R33 |
| R34 → R35 → R36 → R37 | Chastity session tracking → check-ins → release requests → consequence integration | roadmap R34–R37 |
| R45 | Compound/multi-phase tasks | roadmap R45 |
| R46 | Communication priority/category on notes | roadmap R46 |

## Depth / formalization

| Item | What | Ref |
|------|------|-----|
| R2 → R22 → R23 | Bilateral contract editing → digital signatures → renewal/expiry | roadmap R2/R22/R23 |
| R19 | Mood trend visualization + dip alerts | roadmap R19 |
| R29 | Scheduled dynamic reviews | roadmap R29 |
| R28 → R44 | Training stages → monthly scored evaluation rubric | roadmap R28/R44 |
| R20 / R21 | Mantra/affirmation rituals; wellness check-in reminders | roadmap R20/R21 |

## Later / big rewrites

| Item | What | Ref |
|------|------|-----|
| R8 + R25 | Stealth PWA + discreet branding | roadmap R8/R25 |
| R16 | Feature/privilege restriction periods | roadmap R16 |
| R30 | Solo self-discipline mode (auth refactor) | roadmap R30 |
| R41 | Dynamic scope level | roadmap R41 |
| H6 / BUG-011 | Optimize per-load N+1 in `_auto_assign_reserves` if scale grows | BUGS.md |

## Definition of done (every backlog item)

- Portable SQL only (no dialect-specific syntax); works on SQLite (tests) and
  PostgreSQL (prod).
- Tests added/updated; full suite green (`pytest`).
- Lint/type/security gates pass (`ruff check`, `ruff format --check`, `mypy`,
  `bandit`).
- Relevant devdocs updated (`data-model.md`, `task-system.md`, `roadmap.md`,
  this file, and user-facing docs where behaviour changes).
- Accessibility preserved (contrast, focus states) for any UI change.
