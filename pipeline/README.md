# moviewords pipeline

End-to-end data pipeline: download OPUS subtitles, curate to top-voted films, parse
words, count frequencies, enrich with TMDB metadata, and derive per-movie/cross-film
word statistics.

## Prerequisites

Before running the pipeline, ensure you have:

- **uv** — Python package manager (https://astral.sh/uv)
- **rclone** — Sync tool for R2 upload (https://rclone.org)
- **~60GB free disk** — the OPUS en corpus alone is ~34GB (never extracted;
  the pipeline streams straight out of the zip). **Optional for `index` and
  `count`:** if `data/raw/opus_en.zip` is absent they read the published zip
  over HTTP range requests instead (`opus_zip.py`) - the index stage fetches
  only the central directory (~2 min), the count stage one ranged GET per
  uncached film (`count --workers 16`: ~22k films in ~14 min from a laptop)
- **TMDB API key** — free, from https://www.themoviedb.org/settings/api.
  Either auth style works: `TMDB_API_TOKEN` (v4 read token, preferred) or
  `TMDB_API_KEY` (v3 key)
- **Cloudflare R2 S3 credentials** — either create in the dashboard
  (R2 → Manage API Tokens), or derive from any CF API token that has R2
  write permission: Access Key ID = the token's id (from
  `GET /client/v4/user/tokens/verify`), Secret = `sha256` hex of the token

No TMDB key / no big disk? Build the 610-film starter dataset instead —
real data (Cornell Movie-Dialogs Corpus) through the same derive stage:

```bash
cd pipeline && uv run python scripts/build_demo_dataset.py
```

## One-Time Setup

Create the R2 bucket (requires Cloudflare account):

```bash
cd pipeline
wrangler r2 bucket create moviewords-data
```

## Full Run

Run stages sequentially from the `pipeline/` directory:

```bash
cd pipeline

# Download ~15–30GB of OPUS OpenSubtitles corpus
# Duration: hours, depending on connection and disk speed
uv run python -m moviewords_pipeline.cli download

# Curate to IMDb votes >= 1000 (see config.py)
uv run python -m moviewords_pipeline.cli curate

# Build corpus index linking IMDb IDs to subtitle zip entries. Each film
# folder holds one file per OpenSubtitles upload (re-synced rips, edits,
# hearing-impaired variants, other translations - and outliers: commentary
# tracks, other films, other languages). corpus_index.rank_candidates
# pre-filters by size (a plausible words/min band at 24.5 raw bytes/word,
# no outsized doubles) and the index stores up to 12 `candidates` spread
# evenly over that ranking.
uv run python -m moviewords_pipeline.cli index

# Parse subtitles and count word frequencies
# Duration: CPU-bound, ~1–3 hours
# Per-movie cache in work/counts/en/ (skips already-processed films)
#
# RUNBOOK NOTE: the tokenizer (wordcount.TOKEN_RE) changed to reject
# digit-adjacent tokens (e.g. "1950s" -> "s", "42nd" -> "nd" junk tokens).
# If you have an existing work/counts/en/ cache built before this change,
# delete it before the first real run afterwards so every film is re-parsed
# with the corrected tokenizer — otherwise stale per-movie caches will keep
# serving counts derived from the old, junk-token-producing regex.
#   rm -rf ../data/work/counts/
# (Since 2026-09-24 bumping config.FINGERPRINT_VERSION does this for you;
# SELECTION_VERSION re-makes choices from cached fingerprints.)
#
# The count stage chooses each film's file by CONTENT CONSENSUS
# (consensus.py): it fingerprints every candidate, drops commentary tracks,
# other-language, sparse and tiny files, then takes the most typical file
# (nearest the median length) of the largest group of agreeing texts
# (content-word cosine >= 0.85; near-identical re-uploads count as one text,
# so a wrong file uploaded 3 times can't outvote real translations).
# Fingerprints are cached per file, so a re-run only fetches new candidates.
# work/selection.parquet records every choice and why. A full recount is
# ~242k reads: ~2h against the remote zip from a laptop; on a VM, download
# the zip and run `count --shard K/N` x N processes (GIL-bound parsing), then
# one unsharded `count` to write the outputs.
uv run python -m moviewords_pipeline.cli count [--workers 12] [--shard K/N]

# Fetch production country and original-language metadata from TMDB
# Duration: ~1.5 hours for ~33k films (throttled ~20 req/s)
# Requires TMDB_API_TOKEN or TMDB_API_KEY environment variable
# Per-movie cache in work/tmdb/ (skips already-fetched films)
TMDB_API_KEY=... uv run python -m moviewords_pipeline.cli enrich

# Derive all published artifacts (parquets, JSON hot paths, decade/genre
# signatures, word_meta with Zipf + WordNet POS classes). First run downloads
# the WordNet data via nltk. Re-run anytime; takes minutes.
uv run python -m moviewords_pipeline.cli derive

# Inspect sanity metrics (expect ~30–40k curated films, >70% TMDB match rate;
# roughly 45% of counted films drop at the original_language == en filter)
cat ../data/out/report.md

# Build the client-side search index (deploy artifact consumed by the app)
uv run python scripts/build_movies_index.py --corpus en
uv run python scripts/build_movies_index.py --corpus all

# Fetch movie posters from TMDB into data/out/posters/ (self-hosted per site
# policy), then encode each to a sibling .avif (needs `avifenc` from libavif).
# Resumable; ~40 min for ~19k films at 8 workers. Encoding alone (e.g. after
# restoring JPEGs from R2) is a few minutes for 51k posters on 14 cores:
uv run python scripts/fetch_posters.py --workers 8
uv run python scripts/encode_posters.py

# Fetch thorough per-film TMDB metadata (one call per film via
# append_to_response=credits,keywords). Writes three tiers:
#   data/work/tmdb_meta/<id>.json     raw response (future-proof, resumable)
#   webdata/out/all/json/blurb/<id>.json  {overview, tagline, runtime} for the app
#   data/out/tmdb_meta.parquet        flat analysis record (credits, keywords,
#                                     collection, budget/revenue, tmdb votes)
# No VM / no recompute: driven by the published movies-index.json id list.
# Resumable (skips cached films); ~45 min for the full corpus at ~20 req/s.
TMDB_API_KEY=... uv run python scripts/fetch_tmdb_meta.py --workers 8

# Upload to R2 (requires env vars CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
# Also copies data/out/posters/*.{jpg,avif} (1y immutable Cache-Control).
# The blurb sidecars ride the long-TTL cache group; tmdb_meta.parquet is
# archived under data/out/ and not auto-published (no app consumer yet).
./scripts/upload_r2.sh
```

## Running on a throwaway cloud VM (how the production dataset was built)

The 2026-09 production run used a GCP `e2-highmem-4` (4 vCPU / 32GB / 200GB
disk, ~$0.19/h) in us-central1 — total wall-clock ~3h: download+curate+index
28 min, count 15 min, enrich 83 min, derive minutes, posters ~40 min. Pattern:

1. `gcloud compute instances create ... --metadata-from-file=startup-script=...
   --metadata=tmdb-key=$TMDB_API_KEY` — the startup script installs uv, clones
   this repo, and runs the stages in sequence, touching `/opt/PIPELINE_DONE`
   or `/opt/PIPELINE_FAILED` marker files.
2. Chain follow-up steps as `systemd-run` transient units that wait on the
   marker files — survives SSH disconnects, observable with short SSH polls
   (`tail /var/log/moviewords*.log`, `ls /opt/*_DONE`).
3. Upload straight from the VM with rclone (stage the derived S3 creds in a
   root-only file, delete after the sync) — datacenter bandwidth beats
   residential by an order of magnitude.
4. Delete the instance when done; the per-movie caches make it cheap to
   recreate later if scope expands.

Gotchas encountered (so you don't re-learn them): `ls A B` in a wait loop
requires BOTH files (use `[ -e A ] || [ -e B ]`); `pkill -f pattern` over SSH
kills your own session if the pattern matches the remote command line (use
`[c]lassic` self-exclusion); rclone→R2 logs harmless `501 NotImplemented`
errors when touching modtimes on unchanged files.

## Resumability & Idempotence

Every stage is resumable and idempotent:

- **count** stage: caches word counts per IMDb ID in `work/counts/en/` (JSON per film).
  If a film is already cached, it is skipped; only new or modified films are re-parsed.

- **enrich** stage: caches TMDB lookups per IMDb ID in `work/tmdb/` (JSON per film).
  If a film is already cached, the API call is skipped.

- **derive** stage: re-reads all cached counts and TMDB data, regenerates reports.
  Safe and fast to re-run anytime.

If the pipeline crashes, re-run the same command to resume from where it left off.

## Scope Expansion

To broaden the film corpus in the future (e.g., lower `MIN_VOTES = 1000` to include
lower-voted films):

1. Edit `src/moviewords_pipeline/config.py` and adjust `MIN_VOTES`
2. Re-run: `curate → index → count → enrich → derive`
   - **curate** will emit a new set of qualified films
   - **index** maps them to subtitle zip entries
   - **count** processes only newly-included films (existing cache entries are reused)
   - **enrich** fetches metadata only for new films (existing TMDB lookups are reused)
   - **derive** regenerates all reports

For additional languages (English-only today, not yet a supported path):

- The `LANG`/`OPUS_URL` config knobs and the per-language `work/counts/<lang>/`
  cache layout are designed to make this possible in principle, but the rest of
  the pipeline currently assumes English: `wordcount.TOKEN_RE` only matches
  `[a-z']` characters (no accented/non-Latin scripts beyond NFKD-foldable Latin
  ones), and the stopword/profanity wordlists shipped in this package
  (`stopwords_en.txt`, `profanity_en.txt`) are English-only.
- Adding a real second language would require a language-aware tokenizer and
  per-language wordlists in addition to changing `config.py` and `OPUS_URL`.

## Output

Artifacts land in `data/out/`:

- `movies.parquet` — one row per published film: IMDb id, title, year,
  countries, genres, runtime, rating, votes, word-count stats
- `words_by_movie/data.parquet` — per-movie word counts, ordered by
  `(imdb_id ASC, count DESC)`
- `words_by_word/data.parquet` — per-movie word counts, ordered by
  `(word ASC, imdb_id ASC)`
- `word_year.parquet` — annual word frequency trends (words with corpus-wide
  count >= 20 only)
- `word_meta.parquet` — per-word Zipf commonness (wordfreq) + WordNet POS
  class letters (n/v/a/r; "x" = unknown to WordNet ≈ names), used by the
  frontend's word filters
- `json/movie/<imdb_id>.json` — per-movie hot-path payload; word entries are
  `[word, value, zipf, classes]` (stats, top words, top incl. stopwords,
  log-odds signature words)
- `json/signature/decades.json`, `json/signature/genres.json` — per-entity
  top + signature words (log-odds vs corpus; a word must appear in ≥3
  distinct films of the entity to qualify)
- `json/leaderboard-default.json` — cross-corpus leaderboard; entries
  `[word, count, movie_count, zipf, classes]`
- `json/wordlists.json` — `{"stopwords": [...], "profanity": [...]}`, the
  same lists the pipeline uses internally, published so the frontend can
  offer a stopword-hiding toggle and compute swearing counts without
  shipping its own copies
- `json/movies-index.json` — slim all-movies search index (built by the
  post-derive snippet in the Full Run section)
- `posters/<imdb_id>.jpg` + `.avif` — TMDB w342 posters (via `scripts/fetch_posters.py`,
  AVIF twin via `scripts/encode_posters.py`); served to the app through `<picture>`
- `json/blurb/<imdb_id>.json` — `{overview, tagline, runtime}` sidecar the movie
  page fetches lazily (via `scripts/fetch_tmdb_meta.py`; written under
  `webdata/out/all/json/blurb/` for publish). Missing files degrade gracefully -
  the page just omits the blurb.
- `tmdb_meta.parquet` — one row per film of thorough TMDB metadata (overview,
  tagline, runtime, release_date, collection, budget/revenue, TMDB
  popularity/votes, genres, keywords, spoken languages, production
  countries/companies, director/writers/composer/cinematographer/producers, top
  cast). Archived for future analyses; not auto-published (no app consumer yet).
- `report.md` — summary statistics and stage-by-stage drop reasons

All outputs are uploaded to the R2 bucket `moviewords-data/` via `upload_r2.sh`.
The full dataset contract and the methodology behind these artifacts are
documented in `../docs/ARCHITECTURE.md`.
