# Review — PR #1: Refactor + Plans for R48 (Probabilistic Proof), R49 (Points & Daily Score), R50 (Noir Theme)

Reviewer: Claude (agent), 2026-09-30
Scope: [github.com/collaed/dscoach PR #1](https://github.com/collaed/dscoach/pull/1) — both commits (refactor; docs/plans)
Method: not a read-only doc review. I fetched the PR branch, ran the actual test
suite (pytest), ran the actual configured lint/security/type gates (ruff,
bandit, mypy) inside a container with the real dependency set, cross-checked
every code claim against `src/` as it exists on the branch, and cross-checked
production (ecb.pm) directly over SSH. Findings below are evidence-backed, not
just doc-review.

**Bottom line up front:** both plans (R48, R49) are well-engineered and should
be built close to as written, with the specific fixes below. R50 is low-risk
and legally sound. The refactor commit is real and should land first. Two bugs
*outside* this PR's scope but touching the same surfaces are more urgent than
anything in this batch and should be fixed before or alongside it — one of
them affects the safe-word button.

---

## 0. Charter baseline used for this review

Pulled from `architecture-v2.md` (Principes directeurs) and
`requirements-complete.md` §8.0 (Guidance real-life & principes d'autorité),
both already on `main`:

1. Modular monolith, Postgres-committed, business logic out of routes.
2. Detection/enforcement via sweep, not page-load (aspirational — not yet built).
3. Media outside the app volume; GDPR/compliance from day one.
4. **Authority features are config, not hardcode** — consent-driven, disclosed,
   per-dyad.
5. **Consequences stay coach-overridable.** Auto-flags never force action.
   The highest escalation tier only alerts, never executes.
6. No investment in scale the product doesn't have (1 coach, 1–2 coachees is
   the actual current deployment — confirmed live on ecb.pm).

I judge every proposal below against these six, not just against internal
consistency.

---

## 1. Refactor commit — verified, not just read

The PR description says "81 tests passing." I did not take that on faith —
I checked out the branch, installed the actual pinned dependency set, and ran
it myself.

| Gate | Claimed | My result | Verdict |
|---|---|---|---|
| `pytest` (SQLite, matches CI env) | 81 passing | **81 passed**, 40s, confirmed independently | ✅ accurate |
| `ruff check src/ tests/` (with the PR's own `pyproject.toml`) | implied clean (listed as a CI gate) | **51 errors**, 45 auto-fixable | ⚠️ not currently clean |
| `bandit -r src/ ... -ll` (exact CI invocation) | implied clean | **4 medium-severity findings** | ⚠️ not currently clean, see below |
| `mypy src/ --ignore-missing-imports --exclude ...` (exact CI invocation) | implied clean | **6 errors**, minor type-hint gaps | ⚠️ not currently clean |

None of these are alarming individually, but **if `ci.yml` is enabled as-is,
the first push to `main` fails on lint/security before any new feature code
is even added.** Recommend: run `ruff check --fix`, address the 6 mypy
annotations, and resolve or justify the 4 bandit findings *before* merging
this PR, so the new required-checks gate doesn't start red on day one.

### Bandit findings, specifically

- `src/ai.py:50`, `src/ai.py:84`, `src/photo_validation.py:228` —
  `urllib.request.urlopen()` (B310, medium). These call fixed, trusted
  inference-API endpoints (Hetzner/Cloudflare), so the risk is low, but
  bandit can't know that. Add a `# nosec B310 — fixed trusted API endpoint,
  not user input` comment at each site so the suppression is documented
  rather than silently masking a real future SSRF if one of these URLs is
  ever built from user input.
- `src/csrf.py:38` — `Markup(f'...{token}...')` (B704, medium). I checked
  `_generate_token()`: it returns `session["_csrf_token"]`, sourced from
  `secrets.token_hex(32)` — not attacker-controlled, so this is a false
  positive. Same fix: a `# nosec B704 — token is server-generated via
  secrets.token_hex, not user input` comment. **This specific change (raw
  f-string → `Markup(...)`) is itself a good fix** — I independently found
  the *unescaped* version during an earlier design review of this repo (an
  f-string returned to Jinja gets auto-escaped, silently breaking the CSRF
  hidden input); this PR already fixes it. Just needs the bandit comment so
  it doesn't look unreviewed.

### Doc-accuracy issues found in this commit's own documentation

- **`marketing.md` §8 and `architecture.md` line 231** both state password
  hashing is "currently sha256... argon2id migration planned/in progress."
  This is **stale**. Argon2id is already implemented and live: `helpers.py`
  already has `_hash_password()`/`_verify_password()` with transparent
  rehash-on-login, new accounts already hash with argon2id, and I personally
  confirmed `argon2-cffi 25.1.0` is installed and exercised in the
  **currently running production container** on ecb.pm. This shipped in the
  "Phase 2: Foundation" commit that is the current tip of `main` — i.e.
  *before* this PR branched. Fix both docs before publishing `marketing.md`;
  right now it under-sells a claim the product can already make honestly.
- **Step 9 of `plan-proof-and-scoring.md`** claims `data-model.md` and
  `task-system.md` were updated "already handled in this batch." I checked:
  **neither file mentions `score_log`, `proof_pct`, or `proof_required`.**
  `roadmap.md`, `backlog.md`, `user-journeys.md`, `marketing.md`, and
  `onboarding.md` genuinely were updated — good — but those two were missed.
  Trivial to fix, but the claim as written is inaccurate.
- `architecture.md:191` names the production image `coaching-coaching:latest`;
  the image actually running on ecb.pm right now is `coaching-phase2:latest`.
  Harmless (the new `ci.yml` deploy job does build `coaching-coaching`, so
  this describes the *future* state correctly) but worth a footnote that
  it's forward-looking, not current.

### A finding this PR's authors could not have known, that changes the priority of "Step 0"

I checked ecb.pm directly before this review: **the `coaching` container had
been stopped for 10 days** (since 2026-09-08), not crashed — `docker inspect`
showed `RestartPolicy=no`, `OOMKilled=false`, no error, meaning it was
deliberately stopped (likely mid-deploy) and nothing ever noticed or
restarted it. I brought it back up and set `--restart unless-stopped` as an
immediate fix.

This is direct, first-hand evidence *for* landing this refactor's CI/CD
pipeline — `ci.yml`'s deploy job already sets `--restart unless-stopped`
(matches the fix I applied by hand), which would prevent a repeat of exactly
this failure mode. **But** the CI health check only runs once, immediately
after deploy — it would not have caught a container that stopped two weeks
*after* a healthy deploy. ecb.pm already runs Uptime Kuma (I can see it in
`docker ps`). Recommend adding `dscoaching.ecb.pm/login` as a monitor there
(5–15 min interval, alert on non-200) as a cheap addition to this same
commit's "Step 0" — it's the actual gap that let this outage run 10 days
unnoticed, and the fix already has the infrastructure sitting idle on the
same box.

**Recommendation for Step 0:** land the refactor commit, but bundle in: (a)
the lint/bandit/mypy cleanup above, (b) an Uptime Kuma monitor for the prod
URL. Both are small, both directly address a real incident, neither changes
scope.

---

## 2. R48 — Probabilistic proof demand

### Feasibility: high, and I verified the integration points

The plan claims 3 call sites need `_roll_proof_required()` wired in. I grepped
`src/` for every `INSERT INTO task_assignment` independently of the plan
document: there are exactly 4 literal insert statements, in
`src/tasks.py:66` (`_auto_assign_reserves`), `src/tasks.py:247`
(`_run_onboarding`), and `src/routes_coach.py:554,603` (two manual-assignment
handlers — matches the plan's "handler(s)" plural). **The plan's enumeration
of integration points is accurate**, not aspirational. `complete_task` is
confirmed at `routes_coachee.py:206`, matching §3.4.

**Correction (caught during cross-review, credit to the PR author's own
independent check):** my grep above was scoped to `tasks.py` and
`routes_coach.py` only, not the whole tree — there is a **5th site**,
`src/automation.py:91`, inside `_run_auto_rules`'s `assign_task` action
branch (an auto-rule can insert a `task_assignment` directly from a coach
automation rule, independent of the assignment paths above). If R48 ships
without wiring the proof-roll into this site too, an auto-rule-triggered
assignment silently bypasses probabilistic proof entirely. The plan's §3.3
insert-site list should add this as a 4th wiring point, and — given that
*this specific enumeration* was wrong once already despite being
independently verified — the implementation step should re-derive the site
list by grep at build time rather than trust either this review's or the
plan's hardcoded list.

### Design quality

- Rolling once at assignment-creation and persisting the result (REQ-48.3),
  rather than re-rolling on display, is the correct call and is explicitly
  justified against the obvious exploit (reload until favorable). Good.
- Cleanly separated from R11 (AI validation) — "demand proof" vs "AI-check the
  proof" are genuinely orthogonal decisions and the plan is explicit that they
  compose rather than conflict. No rework of existing code needed.
- Default `proof_pct=0` preserves current behavior for every existing
  template with zero migration risk (REQ-48.7) — correct backward-compat
  posture.

### Where I'd push back / improve

1. **Charter alignment gap: no disclosure requirement.** Principle 4 above
   ("authority features are config, not hardcode, consent-driven, disclosed
   per-dyad") is the project's own standing rule — see the existing table in
   `architecture-v2.md` for "réserves indiscernables," "lecture secrète," etc.
   A recurring task that *might* randomly demand photographic proof is
   exactly this category of feature. The plan specifies the coachee sees a
   "📷 Proof required" pill **after** the roll happens on an already-assigned
   task, but nothing tells the coachee *in advance* that a task type uses
   probabilistic proof at all, or at what rate. Add a requirement: the task
   card (or contract) surfaces "this task type may randomly require photo
   proof (~X% of occurrences)" *before* the fact, not just the pill after the
   roll. This is a one-line UI addition, not a redesign, and it's the
   difference between "surprise inspection" (fine, if disclosed and consented
   as a dynamic mechanic — which is exactly what the charter says makes it
   legitimate) and "silent surveillance" (which the charter explicitly treats
   as the failure mode to avoid).
2. **Scope the value prop precisely.** The "why probabilistic proof works"
   argument (intermittent reinforcement, can't predict which occurrence) is
   a real, well-cited behavioral mechanism — but it only applies to
   `recurrence in ('daily', 'weekly')`. On a `recurrence='once'` template,
   `proof_pct` degenerates into a single coin flip with no "unpredictability
   over time" benefit. Not a bug — just don't let the task-creation UI imply
   the behavioral benefit applies to one-off tasks; a short helper-text
   caveat is enough.
3. **Test determinism risk.** REQ-48.1's test plan says "proof_pct=50 with
   seeded random → deterministic mix." If this seeds the *global* `random`
   module, test order becomes load-bearing (any other test that consumes
   randomness before this one shifts the sequence) — a classic source of
   flaky CI. Use a local `random.Random(seed)` instance passed into
   `_roll_proof_required`, not global `random.randint`, so the function is
   pure and the test is order-independent. Small change, real payoff (this
   exact class of bug is what makes test suites flaky months later).
4. **Unaddressed edge case:** what happens to *already-pending* assignments
   when a coach edits an existing template's `proof_pct`? The plan is silent.
   Correct behavior is almost certainly "no retroactive change — the roll
   already happened and is persisted," which is consistent with REQ-48.3, but
   say so explicitly as a requirement so it's tested rather than assumed.

### Opportunity/value: genuinely high

This is the strongest item in the batch. It's a real, currently-felt friction
(the plan's own Motivation section states a real problem — 100%-or-0% proof
is either heavy or toothless) with a correctly-scoped, low-risk, high-leverage
fix. Ship it, with fix #1 (disclosure) as a hard requirement, not a nice-to-have.

---

## 3. R49 — Points & persisted daily score

### Feasibility: high, append-only design is the right call

`score_log` as an immutable, append-only ledger (rather than a mutable
counter) is exactly the right pattern — it mirrors `checkin`'s existing
philosophy (explicitly noted in the plan), makes every rollup a pure
aggregation, supports full audit ("+5 stretching, −3 missed journaling" for
free), and survives future changes to scoring rules without needing a
backfill migration. Good architectural instinct.

The idempotency mechanism (`UniqueConstraint(task_assignment_id, reason)`)
is correct but relies on a subtle SQL property that isn't stated or tested:
in both SQLite and PostgreSQL, `NULL` values in a unique constraint are *not*
considered equal to each other, so multiple manual/`checkin`-sourced awards
(which correctly have `task_assignment_id = NULL`) won't collide with each
other. This is the behavior you want — but since it's implicit standard-SQL
behavior rather than something the schema enforces on its face, add an
explicit test for it ("two manual awards with the same reason and NULL
assignment id both persist") so a future contributor porting this to a
different backend doesn't get surprised.

### Where I'd push back / improve

1. **Real gap: no reversal path for excused misses.** `task_assignment` already
   has `status='excused'` in its existing enum. REQ-49.2 hooks scoring into
   `_freeze_overdue`'s transition to `missed`, but nothing hooks into a later
   transition from `missed` → `excused` (which the coach can presumably still
   do — it's an existing status). Once the penalty row is appended, the
   append-only design makes correction easy (append a compensating
   `+penalty` row, `reason='miss_reversed'`) — but the plan doesn't specify
   it as a requirement or test case, so as written a coach excusing a missed
   task after the fact leaves a stale penalty on the books. This is a direct
   instance of charter principle 5 ("consequences stay coach-overridable") —
   add REQ-49.2b: excusing a previously-scored miss MUST append a
   compensating reversal row.
2. **Redemption balance is unspecified (affects R51, but decide it now).**
   Neither this plan nor R51's one-liner says whether a coachee can redeem
   into negative balance, or whether redemption must be balance-checked.
   Pick one explicitly (my recommendation: validate sufficient balance by
   default, since "debt" as a mechanic is a much bigger design conversation
   than this batch intends) so R51 isn't guessing later.
3. **Two parallel "compliance signals" — deliberate, but say so.** The
   product already has `current_streak`/`best_streak`/`strikes` on `coachee`
   (I confirmed these are untouched, separate columns in `models.py`). R49
   adds a *second*, independently-computed accountability metric on the same
   dashboards. That may be entirely intentional (streak = consistency chain,
   score = weighted magnitude — genuinely different signals), but the plan
   doesn't say so, and Step 7's UI section doesn't address how the two
   widgets coexist without competing for the coachee's attention. This is a
   product decision, not a technical one — worth one paragraph in the plan
   confirming it's deliberate rather than something that fell out of
   R24's split without being re-examined.
4. **Timezone-boundary test is good; extend it.** REQ-49.4's "near midnight"
   test is the right instinct. Also test a coachee whose configured timezone
   changes (DST transition, or the coach edits `coachee.timezone`) mid-day —
   `score_date` computation should be idempotent to a timezone change that
   happens *after* a row is already written (it should not retroactively
   recompute already-persisted `score_date` values). Worth one explicit test
   asserting past rows are immutable under a timezone edit.

### Opportunity/value: high, correctly scoped as a split from R24

The plan is right that R24 (reward catalog/redemption) and "a persisted daily
score with calendar rollups" are different problems that were incorrectly
bundled in the original roadmap entry. Splitting them, and having R51 as the
explicit glue, is the correct sequencing. Approve, with 49.2b (reversal) added
as a hard requirement before merge — everything else above is a should-fix,
not a blocker.

---

## 4. R50 — Noir theme

### Legal position: sound

The §0 reasoning (colors/spacing/layout ideas are not copyrightable; compiled
CSS, class names, and logos are copyrightable/trademarked and are correctly
excluded) is the right line to draw, and the plan is explicit and disciplined
about staying on the safe side of it — no FetLife name, no logo, no lifted
CSS, token-only derivation from the public rendered palette. Nothing to add
here; this is the correct way to do audience-aesthetic-alignment without risk.

### Accuracy check on the plan's own contrast math

I independently recomputed the WCAG relative-luminance contrast ratios the
plan cites in Step 4, since they're a testable claim:

| Pair | Plan's claim | My calculation | 
|---|---|---|
| body `#a9a9a9` on `#1a1a1a` | ≈ 6.2 : 1 | **≈ 7.40 : 1** |
| headings `#d8d8d8` on `#1a1a1a` | ≈ 10 : 1 | **≈ 12.23 : 1** |

Both numbers in the plan are *understated* — the actual theme is better than
claimed, comfortably clearing not just AA (4.5:1) but AAA (7:1) for normal
text too. Not a problem, just correct the numbers in the doc so a future
contributor doesn't distrust a correct design because the cited math looks
approximate.

### Implementation detail, verified correct

The plan reuses the existing `font_pref` pattern for `theme_pref` (per-coach,
per-coachee, independently selectable). I checked: `font_pref` is read from
`session` at request time (`helpers.py::inject_helpers`), populated at login
from the logged-in user's own row — so coach and coachee already have fully
independent preferences today, not an inherited/shared one. `theme_pref`
following the identical pattern is correct and requires no new mechanism.

### Opportunity/value: medium, correctly prioritized below R48/R49

This is real strategic value (audience fit, a legitimate hook for the stated
future-cooperation goal) but zero functional/accountability value. The
backlog correctly places it as "Now" only because it's cheap and additive,
not because it's urgent — agree with that framing. No objection to shipping
it in the same batch given how low the risk is (pure CSS addition, opt-in,
doesn't touch schema).

---

## 5. R51 and the Harvested items (H1–H9)

### R51 (R24 ↔ R49 integration)

Correctly sequenced as a follow-up, not bundled now. Only addition: see R49
point 2 above (balance validation) — decide it before R51 is built, not
during.

### H1 / BUG-017 (cascade delete gap) — agree this is the most urgent harvested item, and here's how to make the fix durable

The current proposed fix (add the 11 missing tables to the existing hardcoded
cascade list in `admin_delete_coach`) will work, but it's the same shape of
bug that created BUG-017 in the first place — someone will add table #32 next
quarter and forget to add it to the list again. Stronger fix: derive the
cascade list from `models.py`'s own `ForeignKey` metadata (SQLAlchemy exposes
this via `Table.foreign_keys` / `metadata.sorted_tables`) so that deleting a
coach walks every table with a FK to `coach.id`/`coachee.id` automatically.
Then add a test that asserts *zero orphaned rows in any table* after
`admin_delete_coach`, computed generically (iterate `metadata.tables`, not a
hand-maintained list) — this makes the test itself immune to the next new
table, closing the bug class rather than just this instance of it.

### H2–H9

I reviewed each against the codebase and BUGS.md; the descriptions and
locations are accurate, and the prioritization (H1 now; H3/H4/H7 as quick
wins; H2/H9 folded into their related larger roadmap items; H6 explicitly
deprioritized) matches the charter's own "don't build for scale you don't
have" principle — agree with all of it as triaged. One factual note: H8 (the
"20 tables" docstring) — I confirmed it's still literally present in the
PR's actual `src/models.py:1` today ("20 tables" vs. the real 30/31), so it's
correctly still open, not already fixed by this commit.

### Two items that belong on this list and aren't on it yet

I found these independently during an unrelated design-system review of this
repo, earlier the same day. Neither is in `BUGS.md` or the harvested list —
the harvesting audit says it re-read "all devdocs + BUGS.md," which explains
the miss: both are template-level bugs, not something a docs/code audit of
`routes_*.py`/`app.py` would surface.

- **H10 (proposed) — CSRF token rendered outside its own `<form>` tag.**
  Repeats in at least five templates (`onboarding.html:55`, `week_plan.html:63`,
  `payments.html:66`, `coach_view_coachee.html:267`, and
  **`coachee_dashboard.html:396`**) — a copy-paste artifact of the
  one-line delete/toggle form pattern. The last one is **the safe-word /
  emergency-stop button**. If CSRF validation is enforced server-side (it is
  — `src/csrf.py` validates all POST/PUT/DELETE/PATCH by default), a token
  rendered outside its `<form>` doesn't get submitted with it, and the
  request is rejected. This is the single highest-severity finding across
  everything I've reviewed on this project today: it risks the one control
  the charter treats as an absolute, ungated circuit breaker
  (`requirements-complete.md` §8.0; this PR's own `user-journeys.md` Journey
  8: "never gated by proof or score"). **Recommend fixing this before or
  alongside R48/R49, not after** — it's a one-line-per-template fix (move
  `{{ csrf_field() }}` inside the `<form>...</form>` bounds), trivially
  testable (assert every rendered form's closing tag comes after its csrf
  field), and it is more urgent than any item currently in this PR.
- **H11 (proposed) — secrets exposed in client-side JS.**
  `coach_view_coachee.html:368,410,414` embeds `llm_key` and `tg_token`
  (Telegram bot token) into page JS via `|tojson`, then calls the Telegram
  Bot API directly from the browser using that token. Both secrets are fully
  visible in page source/devtools to anyone who can view the page. Should
  move to a server-side proxy route before this ships to any coach who isn't
  the original author.

I'd suggest adding both to `roadmap.md`'s harvested table and `BUGS.md` as
BUG-018/BUG-019, and treating H10 in particular as a blocking prerequisite —
not because it's part of what this PR set out to do, but because everything
else in this PR (proof, scoring, theme) is happening on top of a dashboard
whose safety-critical control may currently be silently broken.

---

## 6. Recommended merge order

1. **Now, before anything else:** H10 (CSRF-outside-form, especially the
   safe-word button) and H11 (exposed secrets). Small, urgent, unrelated to
   this PR's own scope but touching the same files R48/R49's UI work will
   touch.
2. **This PR, commit 1 (refactor):** land as-is, plus the ruff/bandit/mypy
   cleanup (§1) and an Uptime Kuma monitor for the prod URL. This unblocks
   real CI/CD and would have prevented the 10-day outage I found.
3. **This PR, commit 2 (docs):** approve with the fixes noted — disclosure
   requirement for R48, the 49.2b reversal requirement for R49, the two
   contrast-number corrections for R50, and filling the `data-model.md` /
   `task-system.md` gap the plan claimed was already done.
4. **Implementation, in order:** R48 → R49 → R50 → R51, matching the plan's
   own sequencing; H1 (cascade fix, ideally the metadata-driven version) can
   land in parallel since it touches unrelated code.

## 7. What's genuinely good here, stated plainly

The two plan documents are unusually rigorous for a personal project: every
requirement is numbered and traced to a design section and a test, the
schema changes are minimal and portable (no dialect-specific SQL, verified
against the project's own stated SQLite/PostgreSQL-parity rule), the
anti-gaming reasoning (roll-once-at-creation, not-on-display) is correct and
explicitly justified rather than assumed, and the legal reasoning in R50 is
genuinely sound, not just asserted. The self-audit that produced the
harvested items (H1–H9) is a good practice and found real, accurately-located
bugs. The gaps I found are refinements to a solid plan, not signs of a plan
that needs to be rethought.
