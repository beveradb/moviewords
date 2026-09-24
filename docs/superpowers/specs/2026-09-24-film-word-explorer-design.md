# Film page: "Every word" explorer - design

**Date:** 2026-09-24   **Status:** approved (brainstorm), ready for plan (after trends-per-film ships)
**Why:** users want to ask "how often does *this* film say X?" and share the
answer (e.g. the famous "shiiiit" in Butch Cassidy, 1969). Film pages only show
the top 25 / signature words; the baked `json/movie/<id>.json` holds the top 200.

## Scope

In: a per-film full word-list sidecar; a search box with a linkable `?q=`;
stretched-spelling matching; a sortable, paginated full list; "only in this
film" words.
Out: fixing mismatched subtitle files (handoff #1), counting stretched
spellings in corpus-wide stats.

## Data: `json/words/<imdb_id>.json`

- One file per film in the global `all/` tree (~51.6k), same key scheme as
  `json/blurb/<id>.json`. Shape: `{"w": [[word, count, films], ...]}` sorted by
  count desc, then word; `films` = number of films in the whole corpus whose
  subtitles contain the word (document frequency over `words_by_movie`).
- Every word the film contains (e.g. Butch Cassidy: 1,283 words, 6,537 total -
  matches `unique_words`/`total_words`). ~22 KB raw avg, a few KB brotli.
- New stage `words` in `pipeline/scripts/rebuild_web_data.py` (global corpus
  only; per-movie data is language-independent). Uploaded additively via
  `upload_r2.sh` (new `json/words/**` rule, same Cache-Control as `json/movie/**`)
  - like the blurb sidecars, no existing file changes.

## Frontend (movie page, `app/src/views/Movie.tsx`)

New section "Every word in this film" below the existing word lists.

- **Loading:** `getMovieWords(id)` - own cache, 404-tolerant like
  `getMovieBlurb`; fetched when the section scrolls into view or immediately if
  `?q=` is present. 404 -> "Full word list unavailable for this film"; rest of
  page unaffected.
- **Search box**, bound to `?q=` (`#/movie/tt0064115?q=shit`); typing updates
  the URL (replace, not push). A `?q=` on load scrolls the section into view.
  - Exact match shown first: count, rate per 1k words, "said in N films",
    link to `#/trends?w=<word>`.
  - **Stretched spellings:** also list words `v != q` where `collapse(v) ==
    collapse(q)` **and** `v` has a run of 3+ identical letters (`collapse` =
    squash runs of a repeated letter to one). "shit" matches "shiiiit",
    "shiiiitttt"; "god" does not match "good" (no 3-run). Shown as "also
    written as: shiiiit x1". Works even if the exact word is absent (Butch
    Cassidy has 0 "shit", 1 "shiiiit").
  - Non-empty query also filters the full list below (substring on the word).
- **Full list:** table word / count / per 1k / films-that-say-it; sort by count
  (default), A-Z, or rarest (films asc); 50 per page with prev/next; word links
  to its trend.
- **Only in this film:** up to 10 words with `films == 1` and `count >= 2`,
  alphabetic tokens only (drops one-off typos/fragments), by count desc. Hidden
  if none.

**i18n:** new `movie.*` keys in `en.json`, translated by the pipeline.

## Testing

- Unit (vitest): `collapse` + stretched-variant matching (shit/shiiiit,
  god/good negative, exact-absent case); sort + paginate; "only in this film"
  filter; `?q=` read/write helper.
- Pipeline (pytest): `words` stage output on a tiny fixture (all words, counts,
  df, ordering).
- Playwright: `#/movie/tt0064115?q=shit` shows "shiiiit x1"; 404 film shows the
  unavailable note.

## Ship

Bake `words` (~51.6k files) -> upload -> spot-check 200s -> merge PR
(auto-deploy). Data first, app second (the app degrades gracefully if not).
