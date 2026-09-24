# AVIF posters + 1y immutable poster cache — 2026-09-24

**Project:** moviewords   **Branch/commit:** main @ f4c1bf1 (PR #36 squash-merged, auto-deployed)   **Status:** done — live on prod, verified

## Summary

Executed `docs/handoffs/2026-09-24-avif-posters-and-cache.md`. All 51,600
posters now have an AVIF twin on R2, the app serves them via `<picture>` (AVIF
+ JPEG fallback), every poster object carries `Cache-Control: public,
max-age=31536000, immutable`, and the pipeline produces/publishes both going
forward. PSI "Efficient cache lifetimes" cleared (356 KiB → 4 KiB, only the CF
analytics beacon left); "Improve image delivery" dropped 156 → 134 KiB — the
remainder is *resizing*, not format (see Open threads).

## What changed

**Data / R2 (ops, done outside the PR):**
- Pulled all 51,600 JPEGs from `r2:moviewords-data/posters/` (2.33 GiB) into the
  main clone's `data/out/posters/` (gitignored; still there, ~3.9 GB with AVIFs).
- Encoded with `avifenc -q 60 -s 6 -j 1` (14 cores, ~8.5 min): **2.50 GB JPEG →
  1.44 GB AVIF (−42%)**. Chose q60 after eyeballing q50/q60 vs JPEG at 2× zoom
  (q50 smoothed dark film-grain textures).
- Uploaded AVIFs with the immutable header (rclone, additive copy).
- Set the header on the **existing JPEGs server-side** without re-uploading:
  `aws s3 cp s3://moviewords-data/posters/ s3://moviewords-data/posters/
  --recursive --exclude '*' --include '*.jpg' --metadata-directive REPLACE
  --content-type image/jpeg --cache-control "public, max-age=31536000, immutable"`
  (64 concurrent via a temp `AWS_CONFIG_FILE`; 2m41s; ETags unchanged).
- Purged the zone edge cache (`purge_everything`).
- **Cloudflare cache rule** "Cache moviewords data bucket" (`http.host eq
  data.moviewords.org`) has edge + browser TTL = **respect_origin**, so the
  object header gives 1y at both layers — no rule change needed. Verified
  `.avif`/`.jpg` → 200, correct content-type, 1y immutable, MISS→HIT.

**PR #36** (`perf(posters): serve AVIF via <picture>, cache posters 1y immutable`):
- `app/src/components/ui.tsx` `Poster`: `<picture className="contents">` +
  `<source type="image/avif">` + JPEG `<img>`. `contents` keeps the img as the
  layout box (callers' `w-full`/borders + `aspect-[2/3]` unchanged → CLS 0).
  `onError`: if `currentSrc` ends in `.avif` → drop the `<picture>` and retry
  plain JPEG (`noAvif` state); otherwise text placeholder. Tests in
  `ui.test.tsx`.
- `pipeline/scripts/encode_posters.py` (new): resumable (skips existing
  `.avif`), parallel, `.part.avif` temp + rename, WebP sniff → `magick` → PNG →
  avifenc; fails fast without `avifenc` and **raises if any poster failed**.
  `fetch_posters.py` calls `encode_all()` at the end. Tests in
  `pipeline/tests/test_encode_posters.py`.
- `pipeline/scripts/upload_r2.sh`: new step copies
  `${POSTERS_DIR:-../../../data/out/posters}` `*.{jpg,avif}` (excluding
  `*.part.avif`) with the 1y immutable header; generic 24h rule excludes
  `posters/**`; warns if the dir is missing.
- Docs: `docs/ARCHITECTURE.md`, `docs/DATA.md`, `pipeline/README.md`.

**Ship:** Superpowers review (CodeRabbit CLI SSO-blocked; PR opened without
`@coderabbitai ignore`) → fixed its one Important finding (silent encode
failures) + minors → GitGuardian pass → squash-merge → `deploy` workflow
success → prod bundle `index-BVYdg6FS.js`; homepage 8/8 posters load `.avif`,
0 JPEG fetches, CLS 0.

## Decisions & rationale

- **q60, not the handoff's cq28** — `avifenc` 1.3 deprecates `--min/--max`;
  `-q` is the current knob. q60 ≈ 55% of JPEG size on the sample, visually
  identical at poster sizes.
- **Metadata rewrite in place for JPEGs** instead of re-uploading 2.5 GB —
  server-side CopyObject with `REPLACE`, zero bandwidth.
- **Belt and braces on "every JPEG has an AVIF"** — pipeline raises on any
  failure AND the frontend retries JPEG on AVIF error, so a missing AVIF costs
  bytes, never a poster.
- **No new Python deps** — WebP conversion uses ImageMagick (already
  installed) rather than adding Pillow.
- **No CF rule change** — respect-origin already yields 1y edge + browser.

## Learnings / gotchas

- **`<picture>` does not fall back on 404.** Once the browser picks the AVIF
  `<source>`, a failed load fires `img.onError`; it never tries the `<img src>`
  JPEG. Hence the `noAvif` retry.
- **33 TMDB "posters" are WebP bytes named `.jpg`** (served by R2 as
  `image/jpeg`; browsers sniff so they display fine). `avifenc` rejects them
  ("Unrecognized file format") — sniff `RIFF....WEBP` and convert first.
- **rclone `--checksum` skips unchanged objects, so it never updates their
  headers.** `upload_r2.sh`'s Cache-Control only lands on NEW uploads; change a
  header policy → rewrite metadata server-side (recipe above).
- **`config.OUT_DIR` resolves to the checkout the script runs from** — from a
  worktree it's the worktree's (empty) `data/out`, not the main clone's. Pass
  `--dir` to `encode_posters.py`.
- **HEAD requests to `data.moviewords.org` show `cf-cache-status: DYNAMIC`**;
  use GET to check edge caching.
- **PSI public API hit its daily quota (429)** and the pagespeed MCP returned
  400. Fallback: `npx -y lighthouse@latest <url> --only-categories=performance
  --form-factor=mobile --chrome-flags="--headless=new" --output=json`.
- Cross-origin poster timings show `encodedBodySize` 0 (no
  `Timing-Allow-Origin`) — check `currentSrc` instead to confirm AVIF is used.

## Open threads & next steps

- **Responsive poster sizes (optional):** Lighthouse's remaining ~134 KiB is
  "342px image shown at 180px". Fix = a w185 variant (TMDB `w185`, or
  downscale + AVIF) at `posters/w185/<id>.avif` + `srcSet`/`sizes` in
  `Poster`. Real-device savings are smaller than Lighthouse claims (phones are
  ~2–3× DPR, so 342px is close to needed).
- **Local Lighthouse mobile LCP read 13.5 s** in one throttled run — not
  investigated; worth a proper PSI re-run when quota resets.
- Local poster copies (~3.9 GB) remain in `data/out/posters/` — keep for future
  runs or delete; R2 is the source of truth.
- Carried over: post-HN sharing handoff
  (`docs/handoffs/2026-09-24-post-hn-sharing-strategy.md`); route-level
  code-splitting for unused JS; base `grid-cols-1` in Movie/Home/Entity; make
  `translation-check` a required status check.

## Related docs

- Handoff executed: `docs/handoffs/2026-09-24-avif-posters-and-cache.md`
- Prior session: `docs/sessions/2026-Q3/2026-09-24-launch-day-fixes-and-perf.md`
- PR: https://github.com/beveradb/moviewords/pull/36
