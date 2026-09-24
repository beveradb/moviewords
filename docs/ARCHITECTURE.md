# Architecture & Methodology

How https://moviewords.org works, why it's built this way, and enough
detail to reproduce or extend it. See also the original design spec
(`docs/superpowers/specs/2026-09-11-movie-word-analyzer-design.md`) and the
session records under `docs/sessions/`.

## System overview

```
 OFFLINE (batch, run anywhere — laptop or throwaway cloud VM)
 ┌──────────────────────────────────────────────────────────────┐
 │ OPUS OpenSubtitles v2024 (en, per-movie XML, IMDb ids, ~34GB)│
 │ IMDb non-commercial datasets (title.basics, title.ratings)   │
 │ TMDB API (original_language, production countries, posters)  │
 │        │                                                     │
 │        ▼  pipeline/ (Python 3.12 · uv · duckdb · pyarrow)    │
 │ download → curate → index → count → enrich → derive          │
 └───────────────┬──────────────────────────────────────────────┘
                 ▼  rclone copy (S3 API, additive)
 ┌──────────────────────────────────────────────────────────────┐
 │ Cloudflare R2 (public bucket, custom domain, CORS)           │
 │   parquet: movies · words_by_movie · words_by_word ·         │
 │            word_year · word_meta                             │
 │   json:    movie/<id> · leaderboard · wordlists ·            │
 │            signature/{decades,genres} · movies-index         │
 │   posters/<id>.{avif,jpg} (self-hosted, TMDB-sourced)        │
 └───────────────┬──────────────────────────────────────────────┘
                 ▼  plain fetch (hot paths) + DuckDB-WASM (SQL over
                    HTTP range requests — no backend anywhere)
 ┌──────────────────────────────────────────────────────────────┐
 │ Cloudflare Pages: app/ (Vite · React · TS · Tailwind v4)     │
 └──────────────────────────────────────────────────────────────┘
```

There are **no servers**. Hot paths (movie pages, default leaderboard) are
pre-baked JSON; everything interactive (trends, filtered leaderboards,
word→top-films, swear rates) is DuckDB-WASM in a web worker reading Parquet
directly from R2 with range requests. R2 egress is free, so a traffic spike
costs nothing and hits nobody else's infrastructure.

## The dataset contract

Everything the frontend consumes, published to the R2 bucket root from
`pipeline/webdata/out/` via `pipeline/scripts/upload_r2.sh`:

| Artifact | Contents | Access pattern |
|---|---|---|
| `movies.parquet` | one row/film: imdb_id, title, year, countries, genres, runtime_minutes, rating, votes, total_words, unique_words, words_per_minute, original_language | SQL joins |
| `words_by_movie/data.parquet` | (imdb_id, word, count) **sorted (imdb_id, count DESC)** | per-movie scans (swear counts) |
| `words_by_word/data.parquet` | same rows **sorted (word, imdb_id)** | per-word scans (top films for a word) |
| `word_year.parquet` | (word, year, count, movie_count), corpus-total ≥ 20 | trends |
| `word_meta.parquet` | (word, zipf, classes) for the whole vocab | leaderboard class filters |
| `json/movie/<id>.json` | stats + top/top_all/distinctive; entries `[word, value, zipf, classes]` | movie page (no WASM needed) |
| `json/leaderboard-default.json` | top 1000 (+50 stopwords), entries `[word, count, movies, zipf, classes]` | leaderboard first paint |
| `json/signature/{decades,genres}.json` | per-entity: movie_count, total_words, top[100], signature[100] | entity pages, compare |
| `json/wordlists.json` | stopword + profanity lists | stopword toggle, swear counts |
| `json/movies-index.json` | slim all-movies list (search index) | client-side search |
| `json/featured-series.json` | year totals + per-year counts for the featured words | homepage chart (no WASM needed) |
| `posters/<id>.{avif,jpg}` | TMDB w342 posters, self-hosted; AVIF (q60) + JPEG, cached 1y immutable | `<picture>` (AVIF, JPEG fallback) with text placeholder |
| `all/*` | mirror of every artifact above for the all-films corpus (translated subtitles included) | same access patterns, `all/` prefix |
| `all/word_year_lang.parquet` | (word, year, lang, count, movie_count), corpus-total ≥ 20 per (word, lang) | per-language trends, all-films corpus only |

**The two sort orders are load-bearing**: DuckDB prunes row groups using them,
which is what makes browser-side SQL over a ~45M-row table feel instant. The
same property matters offline — see "performance lessons" below.

## Methodology

**Word counts.** Subtitle XML → cleaned dialogue (`subtitle_parser.py`: strips
timestamps, formatting tags, SDH cues in ()/[] — deliberate, they're cue
delimiters — credit/URL lines, ♪ lines) → tokens (`wordcount.py`). Tokenizer
rules, each motivated by a real artifact found in the corpus and pinned by a
test: lowercase; curly→ASCII apostrophes; apostrophe-run collapse (`don''t`
OCR style); quote-pair stripping that spares contractions/elisions; NFKD
diacritic folding (café→cafe); digit-adjacent rejection (1950s → junk "s");
single-letter noise dropped except a/i; hyphenated words split. **Only bags of
words are ever persisted or published — word order is destroyed at count time
and no subtitle text is redistributed.**

**Corpus cut.** IMDb `titleType=movie`, `numVotes ≥ 300`, matched to OPUS by
IMDb id; one subtitle file chosen per film (largest within a plausibility band
of 20–250 tokens/min of runtime); TMDB `original_language == en` (translated
subtitles measure translators, not screenwriters - both corpora are
published, and the toggle to switch between them ships in the app).

**Signature words** (the product's core idea): log-odds ratio with informative
Dirichlet prior (Monroe, Colaresi & Quinn 2008), the corpus as prior
(`derive.log_odds`, alpha0=100). A movie, a decade, and a genre are all just
bags of words vs the corpus. Entity (decade/genre) signatures additionally
require a word to appear in ≥3 distinct films so a single film's OCR junk or
character name can't dominate.

**Word classes** (`derive.word_meta`): wordfreq Zipf frequency = "commonness"
(UI hides ≥5.0 as "everyday"); WordNet synset POS letters n/v/a/r; words
WordNet doesn't know get class "x" — which in practice is the character-names
class, often the most interesting filter.

**Resumability** (a hard requirement): the two expensive stages keep one cache
file per movie — counts keyed by (language, imdb_id, source zip entry), TMDB
by imdb_id — so any rerun or scope expansion (lower vote floor, TV, more
languages) reprocesses only new items. Caches are written atomically
(tmp + rename) and unreadable cache files are treated as misses, never crashes.

## Toolchain

| Layer | Tools |
|---|---|
| Pipeline | Python 3.12, uv, duckdb, pyarrow, requests, wordfreq, nltk (WordNet), pytest (53 tests incl. fixture-corpus e2e) |
| Data hosting | Cloudflare R2 (free tier: 10GB, free egress), rclone (S3 API; creds derivable from a CF API token: key id = token id from `/user/tokens/verify`, secret = sha256 of the token) |
| Frontend | Vite, React 19, TypeScript, Tailwind v4 (`@theme` tokens; dark mode = token flip on `.dark`), @duckdb/duckdb-wasm (jsDelivr bundles), hand-rolled SVG chart |
| App hosting | Cloudflare Pages (`wrangler pages deploy app/dist --project-name moviewords`) |
| Batch compute | any box with ~60GB disk; we used a throwaway GCP e2-highmem-4 with a startup-script + systemd-run stage chain and `/opt/*_DONE` marker files |
| Verification | Playwright (MCP) against the live site; dataviz palette validator for chart colors (light + dark surfaces, CVD checks) |

## Key decisions log

1. **OPUS bulk corpus over the OpenSubtitles API** — per-movie files with IMDb
   ids, one 34GB download, no rate limits. API reserved for future increments.
2. **Fully static over a backend** — every feature is precomputable or
   expressible as browser-side SQL; zero moving parts, zero hosting cost.
3. **TMDB over OMDb** — no meaningful rate cap (OMDb free = 1k/day); also
   supplies posters. Both v3 key and v4 token auth supported.
4. **Posters self-hosted in R2** — independence from third-party CDNs under
   load; TMDB attribution kept in the footer.
5. **Screenplay visual identity** — Courier Prime, slug-line headers,
   highlighter-mark word bars (the signature element; mark width encodes the
   value). Chart palettes machine-validated for CVD on both surfaces:
   light `#3E6FA8/#CC5A2E/#6B5AA8/#128A5E`, dark `#5B8BC4/#D9744C/#8A77C0/#2FA477`.
6. **English-original-only v1** — see methodology; revisitable - superseded
   2026-09-14: the all-films corpus now ships as a labeled toggle (see the
   dual-corpus spec).
7. **Licensing** — code MIT; published dataset is derived word counts under
   CC BY-NC-SA 4.0 (IMDb non-commercial terms). Attribution required on site:
   OPUS (Lison & Tiedemann 2016), OpenSubtitles.org (corpus condition), IMDb,
   TMDB.

## Performance lessons (hard-won)

- **duckdb-wasm ships with full HTTP reads forced on.** Out of the box (v1.33
  dev builds), every `read_parquet('https://…')` plain-GETs the ENTIRE file -
  93MB for one word's trend - because the runtime skips range detection
  (`forceFullHTTPReads` effectively defaults on). The fix is one `db.open`
  config (`filesystem: { forceFullHTTPReads: false, reliableHeadRequests:
  true }`, see `app/src/lib/duck.ts`), after which the same query moves ~200KB
  of ranged 206s. Verify with devtools: parquet requests must be 206s with
  `Range:` headers, not one big 200. Browser-cache poisoning muddies testing -
  a previously full-downloaded file makes Chrome answer range probes with the
  cached 200, so always verify in a fresh profile/incognito.
- **R2 objects need explicit Cache-Control metadata** (`upload_r2.sh` sets it
  on upload: 5 min for json, 24h for everything else) - without it Cloudflare
  serves every data request from origin (`cf-cache-status: DYNAMIC`) and
  browsers only heuristically cache. Edge caching for `.json`/`.parquet`
  additionally needs a zone Cache Rule (those extensions aren't in
  Cloudflare's default cacheable list).
- **Re-uploads need an edge purge, and per-URL purges miss Vary variants.**
  Data objects serve with `Vary: Origin`, so purging
  `{"files": ["<url>"]}` leaves the per-Origin cached copies alive - name the
  variant (`{"files": [{"url": "<url>", "headers": {"Origin":
  "https://moviewords.org"}}]}`) or purge the whole zone, which is what
  `upload_r2.sh` does after every upload. A stale edge copy of
  `featured-series.json` once silently pushed the homepage onto the full
  ~9MB SQL-engine download; the 5-min json TTL and `loadFeaturedSeries`'s
  console.warn are the backstops against a repeat.
- **Never loop per-movie queries over the big parquet.** Writing the per-movie
  JSONs as 33k individual `WHERE imdb_id = ?` queries ran at ~80 files/min
  (~6h); one streaming pass over the already-sorted parquet with a group-break
  in Python ran at ~10,500/min (~130×). If derive feels slow, this is why.
- The 33k-film count stage itself is fast (~15 min on 4 weak cores) because it
  streams straight out of the zip — never extract the corpus.
- rclone→R2 logs `501 NotImplemented` when it tries to update modtimes on
  files whose bytes didn't change; harmless, syncs converge (`--checksum`).
