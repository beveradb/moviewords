# Handoff: AVIF-encode posters + long cache TTL

**Created:** 2026-09-24 (launch day)   **For:** a fresh Claude session   **Priority:** medium (perf, not a launch blocker)

## Goal

Cut poster weight and fix two PageSpeed reds ("Improve image delivery" ~156 KiB,
"Efficient cache lifetimes" ~356 KiB) by:
1. Encoding all posters to **AVIF** (keep JPEG as fallback).
2. Serving them via `<picture>` (AVIF source + JPEG `<img>` fallback).
3. Giving posters a **long, immutable `Cache-Control`** (they're immutable, keyed
   by imdb id).
4. Baking AVIF + the cache header into the **pipeline** so future poster fetches
   stay covered.

## Current state (verified 2026-09-24)

- **51,600 posters** on R2 bucket `moviewords-data` at `posters/<imdb_id>.jpg`,
  **~2.5 GB total** (avg ~48 KB), TMDB size **w342** (342px wide, 2:3).
- Served at `https://data.moviewords.org/posters/<id>.jpg` (proxied CNAME → R2).
- **No `Cache-Control` header** currently (they were uploaded outside the current
  `upload_r2.sh`, whose non-JSON rule would set 24h). They ARE edge-cached (HIT)
  via the `data.moviewords.org` cache rule, but browsers get no long TTL.
- **Not present locally** — must pull from R2 (fast, exact) or re-fetch from TMDB.
- App usage: `app/src/components/ui.tsx` → `Poster` (line ~135), `POSTER_BASE =
  'https://data.moviewords.org/posters'`, `<img src={`${POSTER_BASE}/${id}.jpg`}
  loading="lazy" aspect-[2/3] object-cover>` with an `onError` → text-placeholder
  fallback. Used on the homepage shelf (8) and each movie page.
- **Encoder available:** `avifenc` (`/opt/homebrew/bin/avifenc`), also
  `magick`/`convert`. No `sharp` / `pillow-avif`.
- Pipeline: `pipeline/scripts/fetch_posters.py` fetches TMDB → `data/out/posters/
  <id>.jpg` (config.OUT_DIR = `data/out`), resumable. NOTE: `upload_r2.sh`
  operates on `pipeline/webdata/out/` — reconcile where posters actually live
  before uploading (there's a `data/out` vs `webdata/out` split to check).

## Plan

### 1. Get the JPGs locally
Derive R2 S3 creds (see `docs/PIPELINE-RESTORE.md` / `moviewords-deploy-ops`
memory): access-key = `GET /user/tokens/verify`.result.id; secret =
`printf '%s' "$MOVIEWORDS_CF_TOKEN" | shasum -a 256 | cut -d' ' -f1`; endpoint
`https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`. Then
`rclone copy r2:moviewords-data/posters/ ./posters-jpg/ --transfers 64`
(or `aws s3 sync`). ~2.5 GB.

### 2. Encode to AVIF (parallel)
`avifenc` per file. Sensible starting point for small photographic posters:
`avifenc --min 0 --max 63 -a end-usage=q -a cq-level=28 -s 6 -j all in.jpg out.avif`
(cq ~26–30 is a good quality/size tradeoff; `-s 6` = speed 6; tune on a sample of
~20 and eyeball). Parallelize with `xargs -P` or GNU parallel across cores.
Expect ~40–55% smaller than JPEG. Do NOT resize (already w342, small). Estimate:
tens of minutes to ~1–2h depending on cores.

### 3. Upload AVIF + fix cache on both
Upload AVIFs to `posters/<id>.avif` AND re-upload the JPGs, both with an
**immutable** header (posters never change):
`rclone copy ./posters-avif/ r2:moviewords-data/posters/ --checksum \
  --header-upload "Cache-Control: public, max-age=31536000, immutable"`
(and same for the jpgs). Then purge the edge cache for `/posters/*` (or
purge_everything) so the new headers take effect.

### 4. App: `<picture>` with AVIF + JPEG fallback
In `Poster` (`app/src/components/ui.tsx`):
```tsx
<picture>
  <source srcSet={`${POSTER_BASE}/${id}.avif`} type="image/avif" />
  <img src={`${POSTER_BASE}/${id}.jpg`} alt={...} loading="lazy"
       onError={() => setFailed(true)} className={`aspect-[2/3] object-cover ...`} />
</picture>
```
Keep the `failed` text-placeholder fallback (the `<img onError>` fires if BOTH
fail). Keep `aspect-[2/3]` so CLS stays 0. AVIF has ~95%+ browser support
(Safari 16+, all modern Chrome/FF) — JPEG covers the rest.

### 5. Bake into the pipeline
- Add an `encode_posters.py` (or extend `fetch_posters.py`) that, after fetching
  each JPEG, also writes `<id>.avif` (idempotent/resumable, skip existing).
- Update `pipeline/scripts/upload_r2.sh`: add a dedicated **first-match** filter
  rule for `posters/**` with `--header-upload "Cache-Control: public,
  max-age=31536000, immutable"` (currently posters would fall into the generic
  non-JSON 24h rule). Remember: rclone `--filter` is first-match-wins; copy
  ADDITIVELY, never `rclone sync`.

## Verify when done
- `curl -sI -H "Accept: image/avif" https://data.moviewords.org/posters/tt0068646.avif`
  → 200, `content-type: image/avif`, `cache-control: ...max-age=31536000, immutable`.
- Chrome DevTools: poster requests fetch `.avif`; Safari/old → `.jpg`.
- Re-run PageSpeed mobile: "Improve image delivery" + "Efficient cache lifetimes"
  should clear; CLS should stay ~0 (aspect-ratio preserved).
- Storage sanity: jpg (2.5GB) + avif (~1–1.5GB) ≈ 3.5–4GB < 10GB R2 free tier.

## Gotchas
- Auto-deploy is live (`.github/workflows/deploy.yml`) — the app `<picture>`
  change deploys on merge to main. The R2 upload is separate (manual/pipeline).
- Purge the CF edge cache after re-uploading posters or the old (header-less)
  cached copies persist.
- Confirm the `data/out/posters` vs `pipeline/webdata/out/posters` path before
  running the upload script.
