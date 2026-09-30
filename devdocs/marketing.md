# marketing.md — DSCoaching Positioning & Go-to-Market

Status: **Draft** for review — 2026-09-30. Internal planning document, not
public copy. Sensitive claims (privacy, safety) must be verified against the
actual implementation before any are published.

## 1. One-line positioning

A free, private, self-hostable accountability platform for structured
1-to-many coaching relationships — built for the kink/D-s community, by someone
inside it.

## 2. Who it's for

- **Primary:** dominants/coaches running structured dynamics with one or more
  submissives/coachees who want real tooling instead of spreadsheets, scattered
  chat apps, and memory.
- **Secondary:** individuals practising self-discipline who want structure before
  entering a dynamic (planned solo mode, R30).
- **Audience overlap:** FetLife's user base. This tool is complementary, not
  competitive — FetLife is social/discovery; DSCoaching is the private
  operational layer for an established relationship.

## 3. Why it exists (the wedge)

Existing options are either generic habit trackers (no authority model, no
contract, no proof/consequence concepts) or closed, paid apps with unclear data
handling. DSCoaching is:

- **Free.**
- **Private by design** — self-hostable; single-tenant Docker + PostgreSQL;
  data export any time; no third-party analytics. *(Verify each claim before
  publishing — see §8.)*
- **Native to the dynamic** — contracts, safe words, rituals, protocol modes,
  consequences, proof, and now adaptive proof + a daily score are first-class,
  not bolted on.

## 4. Differentiators (feature-backed)

| Theme | What we have | Status |
|-------|--------------|--------|
| Authority model | True coach→coachee(s) roles, per-coachee contracts, private coach notes | 🟢 |
| Consent & safety | Digital safe word / pause / stop, always available; audit log | 🟢 |
| Accountability loop | Tasks, recurring/reserve tasks, streaks, strikes, grading | 🟢 |
| Proof | Photo proof + AI validation (advisory, coach overrides) | 🟢 R11 |
| **Adaptive proof** | **Probabilistic proof demand — intermittent verification, less friction, still credible** | 🔴 R48 (planned) |
| **Gamified score** | **Persisted daily points, week (Sun–Sat / Mon–Sun) & month rollups, best week** | 🔴 R49 (planned) |
| Communication | Async notes (pinned/scheduled/read receipts), voice notes, priority (planned) | 🟢 / 🔴 R46 |
| Depth modules | Rituals, creative works archive, mental conditioning, goals, journal, tracking | 🟢 |
| Community aesthetic | Opt-in dark "noir" theme familiar to the target audience | 🔴 R50 (planned) |
| Privacy/stealth | Discreet branding, session timeout, stealth PWA | 🔴 R8/R25/R26 (planned) |
| i18n | English + French | 🟢 |

The two headline additions for the next release — **adaptive proof** and the
**daily score** — are the marketing hooks: "accountability that doesn't exhaust
either of you" and "watch the discipline add up."

## 5. Messaging pillars

1. **Private.** Your dynamic is yours. Self-host it; export it; no ads, no
   tracking. *(Verify.)*
2. **Real, not gimmicky.** Contracts, consent tooling, and consequence systems
   modelled on how these relationships actually work.
3. **Kind to both sides.** Adaptive proof and configurable penalties mean
   accountability without burnout for the coachee or review-fatigue for the
   coach.
4. **Free.** No paywall on the core loop.

## 6. Channels

- FetLife groups/writing relevant to protocol, TPE, structure (respecting each
  group's self-promotion rules).
- Word of mouth within existing dynamics ("stables").
- The in-app help pages already double as onboarding collateral.
- A future public landing page using the noir theme (R50) so first impression
  matches audience expectations.

## 7. Possible FetLife cooperation

If pursued, the aesthetic alignment (R50) is deliberately **token-based and
independently created** (see `plan-aesthetic-noir.md`) — no FetLife marks or CSS
are used — so a formal partnership (official palette, co-branding, or SSO) would
be a clean additive step, not a cleanup of copied assets. Any use of the FetLife
name/logo waits for a signed agreement.

## 8. Claims to verify before publishing (compliance)

Do not publish these until confirmed against code and deployment:

- "No third-party analytics / no tracking" — audit the templates and headers.
- "Self-hostable" — confirm the Docker path is documented end-to-end
  (`deployment.md`).
- "Data export any time" — `/me/export` exists (🟢) but confirm it covers newer
  tables.
- "Private by design" — review session security, at-rest handling, and the
  hardcoded email issue (BUG-007 / H4) before claiming privacy maturity.
- Password storage is currently sha256 hex (no salt) — do **not** market strong
  credential security until this is upgraded (argon2id foundation is in
  progress per the last commit).

## 9. Non-goals / guardrails

- Not a discovery/social/dating product (that's FetLife's space).
- No claims of professional (medical/psychological/legal) advice.
- Marketing must reflect the consent-first, safety-first design — never frame
  consequence/chastity features in a way that omits the safe-word circuit
  breaker.
