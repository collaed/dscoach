# IDEAS.md — Idea Capture

Lightweight, low-friction capture for ideas before they're formalized. This is
the *inbox*; once an idea is fleshed out it graduates to a numbered roadmap item
(`devdocs/roadmap.md`) and, if it needs a design, a `devdocs/plan-*.md`.

Status key: 💭 raw · 🌱 exploring · 📋 promoted to roadmap · ❄️ parked

Add new ideas at the top of "Open Ideas". Keep each entry short; link out to a
plan doc if one exists.

---

## Open Ideas

### Contract drafting from pre-written sections + sample tasks — 📋 promoted (R52)

**Reconciled 2026-09-30**: two independent drafts of this idea converged the
same day. Merged into one plan — real extracted seed data (20 sections + 23
tasks from an actual contract, name-genericized) plus the simpler
2-table "scaffold, not schema" architecture, with propose/negotiate/sign
composing R2+R22 instead of new tables. See `plan-contract-drafting.md` §7
for exactly what came from which draft and why.

**Vibe:** the coach drafts a contract by picking pre-written **sections**
(building blocks), editing the assembled text, and each section is
**associated with sample task templates** so the contract and the day-to-day
tasks are authored together instead of separately.

- Section library: system-default clauses (shipped) + per-coach private ones,
  cloneable, grouped by category (protocol, communication, rituals, wellness,
  discipline, boundaries, logistics, aftercare, review).
- Choosing a section offers its sample tasks (with R48 `proof_pct` / R49
  `points` hints); coach accepts/edits/skips — nothing auto-creates.
- Assembled text saves to `contract_text` + `contract_history` unchanged, so
  R2 (bilateral editing), R22 (signatures), R23 (renewal) layer on top.

Full design: [`devdocs/plan-contract-drafting.md`](devdocs/plan-contract-drafting.md).

Sub-threads still open (from the plan's §5):
- Draft-time fill-in placeholders (`{{param:label}}`, e.g. "response window: __ h").
- Should the coachee see which sections composed the contract, or just the text?
- Cross-coach section sharing / marketplace (deferred to v2).
- Sections proposing rituals (R38) / week-plan entries, not just one-off tasks.
- Seed sections bilingually (EN + FR).

> _"more to come"_ on this topic — capture additional contract-drafting ideas
> as sub-bullets here until they're worth folding into the plan doc.

---

## How to use this file

- **Capturing:** drop a heading + a few lines under "Open Ideas". No structure
  required. Tag it 💭.
- **Exploring:** as an idea firms up, add bullets, constraints, questions. Tag 🌱.
- **Promoting:** when it's concrete enough to build, give it an `R##` in
  `roadmap.md` (and a `plan-*.md` if it needs design), tag it 📋 here, and leave
  a one-line pointer. Don't duplicate the full spec in two places.
- **Parking:** if an idea is set aside, tag ❄️ with a one-line reason rather than
  deleting it — parked ideas are still signal.

## Graduated / cross-references

- Probabilistic proof → R48 (`devdocs/plan-proof-and-scoring.md`)
- Points & daily score → R49 (`devdocs/plan-proof-and-scoring.md`)
- FetLife-inspired noir theme → R50 (`devdocs/plan-aesthetic-noir.md`)
- Reward currency (R24 ↔ R49) → R51 (`devdocs/roadmap.md`)
- Contract section drafting → R52 (`devdocs/plan-contract-drafting.md`)
- The full catalogue of considered features lives in `devdocs/roadmap.md`
  (R1–R52) and the prioritized queue in `devdocs/backlog.md`.
