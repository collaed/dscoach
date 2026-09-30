# Plan — FetLife-Inspired Aesthetic (Design Tokens)

Status: **Proposed** (for review) — 2026-09-30
Roadmap ID: **R50** (Aesthetic alignment)

## 0. Legal position (read first)

The goal is a dark, understated, kink-community-native look that feels *familiar*
to FetLife's user base — the intended audience for this free tool, and a possible
future cooperation partner.

What this plan does **and does not** do:

- ✅ **Derive design tokens** — colour values, spacing rhythm, type scale,
  component shapes — by observing FetLife's public presentation. Colours,
  measurements, and layout *ideas* are not copyrightable.
- ✅ **Write our own clean CSS** expressing those tokens, layered on the existing
  `static/style.css` token system.
- ❌ **Not copy FetLife's stylesheet, class names, sprites, fonts, or logo.** Their
  compiled CSS is a copyrighted work and their marks are trademarks. Copying it
  verbatim would expose the project to a takedown and would poison any future
  partnership conversation — the opposite of the stated goal.
- ❌ **Not imply endorsement.** No FetLife logo, no "FetLife" in our branding,
  until/unless a cooperation is formally agreed.

Practical note from investigation: FetLife's application CSS is bundled behind
authentication / their asset pipeline and is **not** reachable as a plain
`.css` link from the public site, so there is nothing to "pull and reuse" even
if we wanted to. The tokens below are derived from the publicly rendered
palette (near-black background `#1b1b1b`; text greys `#ccc` / `#aaa` / `#777`)
plus FetLife's well-known crimson/dark-red brand accent.

## 1. What characterises the look

1. **Near-black, warm-neutral background** — not pure black, not blue-black.
2. **A single confident red accent** (crimson leaning dark) used sparingly for
   primary actions and the wordmark, never as large fills.
3. **A calm grey text hierarchy** — bright grey for headings, mid grey for body,
   dim grey for meta.
4. **Flat, low-chrome surfaces** — minimal shadows, hairline borders, restrained
   radii. Content-first, "utilitarian but cared-for".
5. **Dense, readable typography** — a neutral humanist sans; content over
   ornament.

## 2. Gap vs. current theme

`static/style.css` today is already dark and token-driven (good foundation) but:

- `--bg: #0f0f1a` and `--card: #1c1c2e` are **blue-black**; FetLife is
  **warm neutral near-black**.
- `--accent: #e94560` is a **pink-red**; FetLife's accent is a **deeper crimson**.
- Shadows are fairly heavy (`--shadow-lg: 0 12px 40px`); the target look is
  flatter.

So this is a **re-tokenisation**, not a rewrite — change the CSS variables, keep
the structure, ship a new named theme.

## 3. Proposed token set — theme `noir`

Add a body class `theme-noir` (alongside the existing `font-*` themes) so the
look is opt-in per coach/coachee and the current default is preserved for anyone
who prefers it. Coaches already customise `accent/bg/card` via branding — this
theme becomes a one-click preset that sets those.

```css
body.theme-noir {
  /* warm near-black surfaces (derived, not copied) */
  --bg:          #1a1a1a;
  --bg-elevated: #202020;
  --card:        #242424;
  --card-hover:  #2b2b2b;
  --input:       #1c1c1c;
  --input-focus: #262626;

  /* grey text hierarchy */
  --text:           #d8d8d8;   /* headings / primary */
  --text-secondary: #a9a9a9;   /* body */
  --muted:          #767676;   /* meta */

  /* single crimson accent, used sparingly */
  --accent:        #b3153a;    /* crimson, dark-leaning */
  --accent-hover:  #d02348;
  --accent-subtle: rgba(179, 21, 58, 0.10);

  /* hairline borders, flatter elevation */
  --border:        rgba(255,255,255,0.07);
  --border-strong: rgba(255,255,255,0.14);
  --radius:    8px;
  --radius-sm: 5px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
  --shadow-md: 0 3px 8px rgba(0,0,0,0.45);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);

  /* status colours kept but slightly desaturated to sit on warm black */
  --ok:     #3fa66a;
  --warn:   #d99b2b;
  --danger: #d0453f;
}
```

Type scale and fonts stay as-is (`IBM Plex Sans` default is a good neutral
humanist sans and is already loaded); `font-classic`/`font-sharp`/`font-modern`
remain available. No new web-font dependency.

## 4. Implementation steps

- **Step 1** — Add the `body.theme-noir { … }` block to `static/style.css`
  after the existing `font-*` theme blocks. Pure addition; default theme
  untouched (safe, reversible).
- **Step 2** — Add a `theme_pref` selector wherever `font_pref` is already
  chosen (coach settings + coachee, both stored in the same way as `font_pref`
  which already exists on `coach`/`coachee`). Render `theme-{{ theme_pref }}` on
  `<body>` next to `font-{{ font_pref }}`.
- **Step 3** — Offer "Noir (community dark)" as a **branding preset** in
  `/coach/branding`: one click sets `accent_color=#b3153a`, `bg_color=#1a1a1a`,
  `card_color=#242424` for coaches who prefer per-brand colours over the CSS
  theme.
- **Step 4** — Visual QA pass on: login, coach dashboard, coachee dashboard
  tabs, task cards, grading, forms, error pages. Check contrast (WCAG AA:
  body text `#a9a9a9` on `#1a1a1a` ≈ 6.2:1 ✓; headings `#d8d8d8` ≈ 10:1 ✓;
  accent `#b3153a` for large text/icons only, not small body copy).
- **Step 5** — Screenshot before/after in the PR for review.

## 5. Accessibility (non-negotiable, per coding standard)

- Body/meta greys chosen to clear WCAG AA on the warm-black background (values
  in Step 4).
- The crimson accent is reserved for buttons, links, icons, and the wordmark —
  never for small body text, where its contrast on `#1a1a1a` is marginal.
- Focus rings retained (do not remove outlines); use `--accent` at full opacity
  for focus visibility.

## 6. Risks

- **Brand confusion / trademark** — mitigated by §0: no logo, no name, tokens
  only, opt-in theme.
- **Contrast regressions** — mitigated by the Step 4 QA pass with measured
  ratios.
- **Coach brand overrides** — coaches who set custom colours are unaffected;
  the theme is a preset, not a lock.

## 7. If a cooperation with FetLife is pursued

Keep this theme token-based and clearly our own so that any future, *formal*
brand alignment (official palette, co-branding, SSO) is a clean additive step
rather than an unwinding of copied assets. Document the derivation (this file)
as evidence of independent creation.
