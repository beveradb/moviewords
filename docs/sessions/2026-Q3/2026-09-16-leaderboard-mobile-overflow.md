# Leaderboard mobile viewport overflow — 2026-09-16

**Project:** moviewords   **Branch/commit:** main @ 349110d (PR #27 merged & deployed)   **Status:** done — live on prod, verified

## Summary

Fixed a mobile layout bug where the Leaderboard boards overflowed the viewport
horizontally — the card's right border, the "see all →" link, and the trailing
count/value columns were clipped off-screen. Shipped end-to-end (branch → local
Superpowers review → PR #27 → squash-merge → manual wrangler deploy → prod
verification at mobile width).

## What changed

**PR #27** (`fix(leaderboard): stop board grids overflowing the viewport on
mobile`, squash-merged). One file, 3 lines: `app/src/components/boards.tsx` —
added a base `grid-cols-1` to the three responsive board grids:

- `OverviewBoard`  → `grid grid-cols-1 gap-4 md:grid-cols-2`
- `FilmsBoard`     → `grid grid-cols-1 gap-x-10 gap-y-8 md:grid-cols-2`
- `ShiftsBoard`    → `grid grid-cols-1 gap-10 md:grid-cols-2`

Deployed manually (Pages is NOT git-connected, see [[moviewords-deploy-ops]]):
```
cd app && npm install && npm run build
CLOUDFLARE_API_TOKEN=$MOVIEWORDS_CF_TOKEN npx wrangler pages deploy dist \
  --project-name moviewords --branch main --commit-dirty=true
```
Prod bundle `index-D0pXgxBk.js` live on moviewords.org.

## Root cause

The boards were declared `grid ... md:grid-cols-2` with **no base
`grid-cols-1`**. Tailwind's `md:grid-cols-2` = `repeat(2, minmax(0,1fr))` —
tracks that can shrink below content — so desktop was fine. But **below the `md`
breakpoint there is no `grid-template-columns` at all**, so the grid falls back
to a single *implicit* `auto` column. An `auto` grid track sizes to its items'
**max-content** and overflows its container rather than shrinking to it. The
widest card's max-content (a long, un-truncated film title, or the un-wrapped
blurb line) blew the column past the viewport.

Measured at 390px wide (clientWidth resolved to 500 in headless):

| Tab | Container | Grid column resolved to | Overflow |
|-----|-----------|------------------------|----------|
| Overview | 468px | 520px | 36px |
| Film superlatives | 468px | 790px | 306px |
| Risers & fallers | 468px | 468px | none (same latent pattern, didn't manifest) |

Adding `grid-cols-1` makes the mobile column `minmax(0,1fr)` too → it shrinks to
the container and lets the existing `truncate` / `min-w-0` on the inner rows do
their job. Confirmed the fix live by forcing `minmax(0,1fr)` (docScroll 536→500)
before editing, then again post-deploy (all 3 tabs: 0px overflow).

## Decisions & rationale

- **Scoped the fix to `boards.tsx` only.** The same `md:grid-cols-2`-without-a-
  base pattern also exists in `Movie.tsx:142`, `Home.tsx:25`, `Entity.tsx:82`,
  but I verified against prod at mobile width that those pages do NOT currently
  overflow (their single-column content fits 468px). Fixed only where the bug
  actually manifests; left the others as a noted follow-up rather than
  speculative scope creep.
- **Opened PR WITHOUT `@coderabbitai ignore`.** CodeRabbit CLI is SSO-blocked
  (see [[moviewords-dev-gotchas]]); I ran the Superpowers `/code-review` instead
  (clean, no findings). Per the global rule, a non-CodeRabbit local review means
  the `@coderabbitai ignore` line is omitted so the GitHub bot reviews it.
- **No version bump** — `package.json` is `0.0.0` (web app deployed via wrangler,
  not a published package).

## Learnings / gotchas

- **Tailwind responsive grids need an explicit base `grid-cols-N`.** Writing
  only `grid md:grid-cols-2` leaves an *implicit* `auto` column below `md` that
  overflows on content wider than the viewport. Always pair with `grid-cols-1`
  (or whatever the mobile column count is). This is the actual mechanism: the
  fix is not cosmetic — `minmax(0,1fr)` vs `auto` is what allows shrink-to-fit.
- **Diagnosing horizontal overflow:** compare `document.documentElement.scrollWidth`
  vs `clientWidth`, then read the offending grid's computed `gridTemplateColumns`
  — a track wider than the container is the smoking gun.
- **Verifying a prod deploy in an already-open SPA tab:** hash-route navigation
  does NOT refetch the JS bundle, so the old code keeps running. Do a hard
  reload (`ignoreCache`) after deploy, or you'll measure stale behavior (I hit
  this — first post-deploy measurement still showed the overflow).

## Open threads & next steps

- **Optional defensive follow-up:** add a base `grid-cols-1` to the same latent
  pattern in `app/src/views/Movie.tsx:142`, `Home.tsx:25`, `Entity.tsx:82`.
  Not broken today, but one long title/name away from the same bug.
- Local `node_modules` was missing `@testing-library/react` (it's a declared
  devDependency, just not installed locally) — `npm install` in `app/` fixes it;
  needed for `tsc -b` / `npm test` to pass locally.

## Related docs
- [[moviewords-deploy-ops]] — manual wrangler deploy recipe
- [[moviewords-dev-gotchas]] — vite port 5173, CodeRabbit SSO block
- docs/sessions/2026-Q3/2026-09-15-movie-details-and-filters.md — prior session
