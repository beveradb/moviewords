# Header masthead — mobile layout + "Facts" rename — 2026-09-17

**Project:** moviewords   **Branch/commit:** main @ 9105e9b (PR #28 merged & deployed)   **Status:** done — live on prod, verified

## Summary

Reworked the site header into a compact, two-tier "masthead" that uses space
far more efficiently on mobile. Previously the logo sat alone on the first row
and the corpus/theme/language controls stacked *below* the nav tabs — roughly
five stacked rows on a phone. Now it's two tidy rows at every width. Also
renamed the `LEADERBOARD` nav label to **Facts** so the 6-item nav fits a single
row down to 360px. Shipped end-to-end (worktree → PR #28 → squash-merge → manual
wrangler deploy → prod verification at 360/390/1100px).

## What changed

**PR #28** (`feat(header): compact two-tier masthead, tidy mobile layout`,
squash-merged). Files:

- `app/src/App.tsx` — header restructured from a single `flex flex-wrap
  justify-between` row into `flex flex-col gap-3`:
  - **Utility row** (`flex flex-wrap items-center gap-x-3 gap-y-2`): logo with
    `mr-auto`, then a `flex items-center gap-1.5` group of the three controls
    (LanguageFilter / ThemeToggle / LanguageSelector) pushed to the right.
  - **Nav row** (`flex flex-wrap gap-0.5 md:gap-1`): the 6 tab links on their
    own row; tab padding tightened `px-3 py-1.5` → `px-2.5 py-1.5`.
  - Header padding `py-4` → `py-3`; the `gap-3` between the two rows was chosen
    so the space *above* the nav matches the space *below* it (header `py-3`
    bottom = 12px), per Andrew's spacing nit.
  - ThemeToggle: label wrapped in `<span className="hidden sm:inline">` (icon
    only on mobile); button `px-2.5 py-1` → `h-8 px-2`.
  - LanguageFilter: label wrapped in `<span className={active.length === 0 ?
    'hidden sm:inline' : ''}>` — hidden on mobile **only** in the default
    "all films" state; stays visible when a language filter is active so the
    narrowed corpus is still obvious. Button `px-2.5 py-1` → `h-8 px-2`.
- `app/src/components/LanguageSelector.tsx` — flag button `px-2.5 py-1` → `h-8
  px-2` (already `hidden sm:inline` on the native name).
- `app/src/messages/en.json` — `nav.leaderboard`: "Leaderboard" → **"Facts"**.
  Route (`#/leaderboard`), component (`LeaderboardView`), and type names are
  unchanged — display label only.
- All 32 locale files regenerated via the i18n pipeline (delta mode, 1 key
  each). Sample: es "Datos", fr "Faits", de "Fakten", ja "豆知識".

**Deploy** (Pages is NOT git-connected — manual wrangler, see
[[moviewords-deploy-ops]]):
```
cd app && npm run build
CLOUDFLARE_API_TOKEN=$MOVIEWORDS_CF_TOKEN npx wrangler pages deploy dist \
  --project-name moviewords --branch main --commit-dirty=true
```
Prod bundle `index-DlSFjt5P.js` live on moviewords.org.

## Decisions & rationale

- **Two-tier masthead on ALL breakpoints** (not a flex-`order` swap that keeps
  desktop single-row). At the `max-w-5xl` (1024px) cap, logo + 6 nav items +
  labelled controls can't share one row anyway, so the "smart" order-swap just
  produced an awkward lonely controls row. A consistent top-utility-row + nav-row
  masthead is simpler and fits the newspaper aesthetic.
- **Icon-collapse controls on mobile** rather than shrinking text — the only way
  to fit all three controls beside the logo at 360px.
- **Rename Leaderboard → "Facts"** (Andrew's pick over Curios/Records). That
  section is Overview / Top words / Risers & fallers / Film superlatives /
  One-film wonders / Said-by-every-film — records + trivia, so "Facts" is the
  most accurate short umbrella. Kept the route/component names so nothing else
  breaks.
- **Opened PR without `@coderabbitai ignore`** — CodeRabbit CLI is SSO-blocked
  (see [[moviewords-dev-gotchas]]), so no local CodeRabbit pass was possible;
  left the GitHub bot to review per the global rule.

## Learnings / gotchas

- **Uniform control heights need an explicit `h-8`.** Buttons whose content was
  text vs a bare SVG icon vs an emoji flag rendered at three different heights
  (line-height / glyph-metric differences). Fixed height + `items-center` makes
  them match; `py-1` alone did not.
- **Post-deploy stale-chunk blank screen.** Right after the wrangler deploy,
  moviewords.org rendered blank with console `Failed to load module script:
  ... MIME type "text/html"`. Cause: a **cached old `index.html`** referencing a
  previous build's chunk hash that now 404s → SPA fallback returns HTML. A
  hard reload (ignore cache) fixed it; the new bundle serves correctly
  (`content-type: application/javascript`). This is inherent to the manual
  Pages deploy + SPA caching, not specific to this change — expect a brief
  window where returning visitors need a refresh.
- **i18n hook is non-blocking and value-safe.** `.githooks/pre-commit` re-runs
  `translate.py --target all --skip-review` when `en.json` is staged; on GCP
  auth failure it commits anyway (CI only checks *key* parity, which a
  value-only edit preserves). Auth worked this session (ADC, project
  nomadkaraoke).
- **`gh pr merge --squash --delete-branch` fails the local checkout** when run
  from a worktree because `main` is held by the primary worktree
  (`fatal: 'main' is already used by worktree`). The **GitHub-side merge still
  succeeds** — verify with `gh pr view <n> --json state`; just update main
  separately.
- Linter is `oxlint` (`npm run lint`); it reports 3 pre-existing
  rules-of-hooks errors in `LineChart.tsx` on main — unrelated, not a CI gate
  (only `i18n.yml` runs in CI).

## Open threads & next steps

- None blocking. Possible future polish: consider a cache-busting/versioned
  `index.html` or a "new version available, refresh" toast to avoid the
  post-deploy stale-chunk blank screen for returning visitors.

## Related docs

- [[moviewords-deploy-ops]] — manual wrangler deploy recipe, CF token.
- [[moviewords-dev-gotchas]] — port 5173, CodeRabbit SSO block.
- `docs/sessions/2026-Q3/2026-09-16-leaderboard-mobile-overflow.md` — prior
  mobile layout fix (PR #27).
