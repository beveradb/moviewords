# Launch day: Show HN, R2 outage, auto-deploy, perf hardening — 2026-09-24

**Project:** moviewords   **Branch/commit:** main @ (PRs #29–#34 all merged & auto-deployed)   **Status:** launched (Show HN live), site healthy, several perf/SEO/AI-discoverability fixes shipped. Two follow-ups handed off (see Open threads).

## Summary

Prepped and executed the public launch of moviewords.org (Show HN), fixed a
site-down incident mid-prep, stood up automatic deploys, and cleared a run of
PageSpeed / agent-discoverability audits. The Show HN went live at
**https://news.ycombinator.com/item?id=49829886** (~12:51 UTC) — quiet as of
handoff. Everything shipped through a new GitHub Actions → Cloudflare Pages
auto-deploy (no more manual wrangler).

## What shipped (all live)

- **PR #29** — refreshed the social share card: `og:`/`twitter:` text
  (18,761→51,624 films; "scripts"→"films") + a **regenerated `og.png`** built
  from HTML→Playwright screenshot with the real clapperboard logo, correct
  domain (was the old `moviewords.beveradb.com`), 51,624 films, 326M words.
  Source saved at `docs/launch/og-card.source.html`.
- **PR #30** — finalized the Show HN copy (`docs/launch/hn-show-hn.md`) per HN
  guidance (rewrite by hand, factual language, no upvote-asking).
- **PR #31** — **auto-deploy** (`.github/workflows/deploy.yml`: build + wrangler
  pages deploy on push to main touching `app/**`) + fixed stale homepage hero
  fallback numbers (`18,000/126M` → `51,624/328M`) in `app/src/views/Home.tsx`.
- **PR #32** — **`llms.txt`** + **`ai-catalog.json`** (ARD v1.0, validated
  against the official schema) under `app/public/` (also `/.well-known/`).
- **PR #33** — **`robots.txt`** (was 404→SPA HTML→44 parse errors) + **CLS fix**
  (0.368→0.032): poster shelf always-rendered with skeletons (was conditionally
  rendered and popped in on data load); `FeaturedChart` body wrapped in
  `min-h-[210px]`.
- **PR #34** — **self-hosted Courier Prime + Inter** (11 subsetted woff2 in
  `app/public/fonts`, `app/src/fonts.css`, preload the 2 above-the-fold latin
  files, `_headers` caches `/fonts/*` 1y immutable). Removed render-blocking
  Google Fonts; LCP element (hero `<h1>`) no longer waits on 3rd-party fonts.
  Verified live: CLS stayed 0.003, no 3rd-party font requests.

## Major incident: R2 subscription removed (site data down)

Mid-prep the homepage showed stale numbers + a broken graph. Root cause: the
**R2 subscription had been removed from the Cloudflare account** (Andrew removed
it thinking it was a paid thing — it's free-tier $0/mo). Effect:
`data.moviewords.org` (R2 bucket `moviewords-data` custom domain) returned R2's
`403 "bucket not publicly accessible"` for every path → all data fetches failed.
**Diagnostic trap:** the CF API returns error **10042 "Please enable R2"** for
ANY token when R2 is disabled — it masks token perms (MOVIEWORDS_CF_TOKEN was
fine all along). Fix: dashboard → R2 → "Add R2 subscription" (free). Restored
instantly; ~1 min of edge propagation flap after. Full writeup in the
`r2-subscription-outage` memory.

## Cloudflare hardening (applied via API, WRITE_ALL token)

- `always_use_https`: off → **on**
- `min_tls_version`: 1.0 → **1.2**
- **HSTS** enabled (max-age 180d, no preload/subdomains)
- Confirmed: SSL Full, edge-caching rule for `data.moviewords.org` already
  present + working (MISS→HIT), R2 CORS correct for range requests, DNS all
  correct, Pages custom domains attached, data brotli-compressed (9.5MB→1.7MB).

## Decisions & rationale

- **Self-host fonts vs async Google Fonts** — self-hosting kills the render-block
  AND avoids the CLS-from-swap risk (preloaded, close-metric fallbacks). Chose it
  over the print-media async trick.
- **Auto-deploy over manual wrangler** — lets Andrew edit content on GitHub
  (incl. mobile) and have it deploy. Path-filtered to `app/**`. Caveat: editing
  `en.json` on GitHub only works for existing strings (new keys need the local
  translate pipeline or the i18n parity CI gate blocks the PR).
- **ai-catalog.json advertises the data files** (not agents/MCP) — the site
  isn't an agent host, so entries point at the JSON/parquet + site; still passes
  the ARD schema and serves the "help AI find the data" goal.
- **Left AVIF + poster cache-TTL as follow-ups** — a multi-hour batch job, not a
  launch-moment change (see handoff).

## Learnings / gotchas

- **R2 disabled → error 10042 masks token scope.** Don't conclude a token is
  under-scoped from 10042; check the R2 subscription first.
- **SPA served `index.html` for any missing root file** → `/llms.txt`,
  `/ai-catalog.json`, `/robots.txt` all failed their audits until real static
  files existed in `app/public/`.
- **CLS from conditionally-rendered sections** — the poster shelf appearing on
  data load was the dominant shift; always-render with skeletons to reserve space.
- **Tailwind v4 `@import "./fonts.css"`** after `@import "tailwindcss"` works;
  `url('/fonts/..')` absolute paths are left as-is by Vite (resolve to publicDir).
- **PSI public API is rate-limited (429)** without a key; measuring CLS/LCP
  directly via `PerformanceObserver({buffered:true})` in the Playwright browser
  is more reliable.
- **Playwright MCP occasionally throws "frame detached"** on navigate — retry /
  open a new tab.

## Open threads & next steps

- **HANDOFF 1 — AVIF posters + cache:**
  `docs/handoffs/2026-09-24-avif-posters-and-cache.md`. 51,600 posters on R2
  (2.5GB) are w342 JPEG with **no cache-control**; encode to AVIF, serve via
  `<picture>` fallback, set immutable cache. Clears PSI "Improve image delivery"
  (156 KiB) + "Efficient cache lifetimes" (356 KiB).
- **HANDOFF 2 — post-HN sharing:**
  `docs/handoffs/2026-09-24-post-hn-sharing-strategy.md`. If the Show HN is a
  bust by afternoon, move to Reddit / PassThePopcorn / Bluesky etc.
- **Other PSI reds (bigger):** reduce unused JS / legacy JS (~100 KiB) →
  route-level code-splitting (a refactor).
- **Monitoring:** GoatCounter (public: moviewords.goatcounter.com) + CF Web
  Analytics (GraphQL, siteTag `e266fdcace664adb85176c3ec4131d5a`). Baseline at
  launch: ~28 CF pageviews / 47 GoatCounter total.

## Related docs

- `docs/launch/hn-show-hn.md` — paste-ready launch drafts (HN/Reddit/PTP/Bluesky)
- Memories: `r2-subscription-outage`, `moviewords-deploy-ops` (now auto-deploy)
