# Trends: MPAA rating filter - design

**Date:** 2026-09-24   **Status:** approved (brainstorm)
**Why:** r/dataisbeautiful asked to "isolate by rating" (e.g. were 80s PG films
spicier?). We promised a rating filter "later today".

## Decisions

- **Trends-only filter** (not site-wide), single select:
  `All ratings | G | PG | PG-13 | R & NC-17/X`, URL param `rating=g|pg|pg13|r`.
  NC-17/X gets only ~5 films/year in the corpus - never enough of its own to
  chart (0 plottable years) - so it folds into the `r` option rather than
  getting its own slice. Composes with multiple words, `per=film` and the
  per-word summary.
- **Source:** TMDB `/movie/{id}/release_dates`, US entry. It is the film's
  *original theatrical* US certification (re-releases can carry a different,
  later certification, which is ignored).
- **Build now** from today's published corpus; re-run fetch (incremental) +
  bake after PR #38 republishes the corpus.
- **Starts at 1968:** with a rating selected, years < 1968 are dropped (MPAA
  ratings began Nov 1968; earlier films only carry later re-release ratings - a
  biased "re-released classics" sample). A note says so.
- **Language filter active -> rating control disabled** with a hint (rating x
  language slices would be ~170 more; rated films are overwhelmingly English).
- **Hidden on the featured chart** (no per-rating featured bake).

## Data

1. `pipeline/scripts/fetch_ratings.py` - ids from the published
   `all/json/movies-index.json`; per film `/find/{imdb}` -> tmdb id, then
   `/movie/{id}/release_dates`. Raw US entries cached per film
   (`<cache>/<imdb_id>.json`, `null` for no TMDB match) - resumable and
   incremental. Certification pick: only US release dates whose certification
   maps to an MPAA bucket (a non-MPAA mark like NR/TV-MA never wins over a
   real MPAA mark on the same film); among those, preferring release type 3
   (theatrical), then 2 (limited), 1 (premiere), then any; earliest date
   within the chosen type - i.e. the film's original theatrical rating, not
   a later re-release's. Buckets:
   `G->g, PG->pg, PG-13->pg13, R->r, NC-17->nc17, X->nc17`; anything else
   (NR, Unrated, missing) -> no rating. Output `webdata/in/all/ratings.parquet`
   `(imdb_id VARCHAR, rating VARCHAR)` for rated films only.
   Sample check (120 English films): ~45% rated; 1968-89 ~75%, 2010+ ~35%.
2. Rating slices, one per `RATING_CODES` entry (`g`, `pg`, `pg13`, `r`) under
   `webdata/in/all/rating/<code>/` = that slice's `movies`, `words_by_movie`,
   and `word_year` re-derived from `words_by_movie` (`SUM(count)`,
   `COUNT(*) AS movie_count` per word+year, same per-word >= 20 floor as the
   language slices). The `r` slice includes both `r`- and `nc17`-rated films
   from `ratings.parquet` (`SLICE_MEMBERS["r"] = ("r", "nc17")` in
   `build_rating_slice.py`); every other slice is just its own code.
   `ratings.parquet` itself keeps `nc17` as its own rating code - no
   information lost there, only folded at slice-build time. Baked with
   `rebuild_web_data.py --corpus all --rating <code> --stage trends` ->
   `webdata/out/all/rating/<code>/json/` `trend/<word>.json`,
   `year-totals.json`, `year-films.json`.
3. `upload_r2.sh`: `all/rating/*/json/trend/**`, `.../year-totals.json`,
   `.../year-films.json` at 1h TTL (same as the language equivalents).

## Frontend

- `data.ts`: `ratingUrl(code, path)` -> `${DATA_BASE}/all/rating/${code}/${path}`.
- `trends.ts`: `RATINGS` (codes + display labels "G", "PG", "PG-13",
  "R & NC-17/X" - MPAA marks, not translated), `ratingFromParams(params)` (valid
  code or null), `RATING_MIN_YEAR = 1968`, `trendsHref(words, { perFilm,
  rating })` (keeps both params).
- `series.ts`: `loadTrends(words, colors, rating)` and the year-map loaders take
  an optional rating; with a rating they read that slice's files (language
  filter ignored - the UI prevents combining), cache keys include the rating,
  rows with year < 1968 are dropped before `toSeries`, and a bake failure does
  **not** fall back to the SQL engine (it can't filter by rating) - it surfaces
  the normal error.
- `Trends.tsx`: a `<select>` (explicit `value` per option) "Rating" beside the
  per-film toggle; changing it navigates via `trendsHref`; data effects re-run
  on rating change. Note: "Based on {count} {rating}-rated films (US MPAA
  rating on theatrical release, via TMDB)." plus "MPAA ratings began in Nov 1968 - earlier films
  are only rated from later re-releases, so the chart starts in 1968."
  Count = sum of the slice's `year-films.json` for years >= 1968.

## Follow-ups (not in this build)

- Investigate pre-1968 rated films (how many; genuine re-release ratings vs
  data errors) - add to the launch follow-ups handoff.
- Re-run fetch + rating bake after PR #38 publishes.

## Testing

- pytest: certification pick + bucket rules; ratings.parquet build from a fake
  cache; rating slice build (movies/words/word_year floor) on a tiny fixture;
  `set_corpus(..., rating=)` paths.
- vitest: `ratingFromParams`, `trendsHref` with both params, rating URLs, the
  1968 trim, no-engine-fallback with rating.
- Playwright (controller): `#/trends?w=fuck&rating=pg`, with `per=film`,
  language filter disables the control, featured hides it, mobile width.

## Ship

Fetch -> bake 4 slices -> upload -> verify 200s -> merge app PR -> prod check
-> Reddit follow-up to hipsterdoofus.
