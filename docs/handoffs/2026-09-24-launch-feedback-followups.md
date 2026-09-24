# Handoff: launch-feedback follow-ups (bad subtitle files, per-film word lookup, MPAA ratings)

**Created:** 2026-09-24 (launch day, afternoon)   **For:** a fresh Claude session   **Priority:** 1 = high (data correctness, visible to users), 2-3 = medium

## Context

The Show HN was auto-killed (spam filter; mods emailed), so we moved on to
Reddit and Bluesky with a single chart - **swearing in English-language films,
1930-2023, with the 1968 Hays Code -> MPAA ratings line**:

- r/dataisbeautiful: https://www.reddit.com/r/dataisbeautiful/comments/1wp34ek/
- Bluesky: https://bsky.app/profile/did:plc:qs7vxexysirqimpz25vnlx4q/post/3mwbiah4mk22e
- Chart + source + data: `docs/launch/swearing-chart.{png,source.html}`,
  `docs/launch/swearing-data.json` (see "Regenerating the chart" below)

Commenters' questions surfaced the three follow-ups below. All numbers are from
the published R2 data (`https://data.moviewords.org/all/...`), checked 2026-09-24.

## 1. Bad / truncated subtitle files (data correctness) - do first

**Problem.** Some films are matched to a subtitle file that isn't the film's full
dialogue. Example: **The Wolf of Wall Street** (tt0993846) has **2,920 words**
for a 180-min film (16 words/min); its top words are "marty, really, characters,
movie, fun, wanted" - a behind-the-scenes featurette. It shows "fucking" x12;
the real film is widely reported at ~569 "fuck"s. Users will notice these
(it's missing from the Trends "most fuck" list, where it should be #1).

**Scale.** Among films with runtime >= 60 min:

| | films | < 30 wpm | < 40 wpm | p5 / p25 / median wpm |
|---|---|---|---|---|
| English-original | 25,324 | 943 (3.7%) | 2,328 | 33 / 53 / 66 |
| non-English | 25,915 | 2,250 | 5,389 | 25 / 43 / 56 |

The < 30 wpm English list mixes **genuinely quiet films** (WALL·E, A Quiet
Place, 2001, Modern Times, City Lights, The Passion of the Christ) with
**clearly broken files**: Superbad (1,408 words), Spider-Man: No Way Home
(1,374), Bohemian Rhapsody (1,154), Project X (1,355), Les Misérables (1,310),
Central Intelligence (953), Vicky Cristina Barcelona (674), 8 Mile, Horrible
Bosses, Cars 2. Likely causes: "forced"/foreign-parts-only subtitle tracks,
extras/featurette files, partial files.

**Aggregate impact is small.** Recomputing decade rates for "fuck"/"shit"
excluding every film < 40 wpm changes them by < 2% (a truncated file contributes
few words, so it has little weight in a per-million rate). The published chart
stands. The damage is at the **film level**: movie pages, per-film rankings
("films that say X the most", Facts superlatives), words-per-minute stats.

**Suggested approach.**
- Detect suspects: low wpm vs runtime (and vs genre - animation/musicals/silents
  run lower), plus a vocabulary check (featurette tells: "movie", "film",
  "character(s)", "scene", "director", cast first names in the top words).
- Where OPUS has multiple subtitle files per film, re-pick the best one (most
  words / closest duration) instead of the current choice. Check how the
  pipeline picks a file today before designing this.
- Otherwise exclude flagged films from per-film rankings (keep or drop from
  aggregates - aggregates barely move either way) and show a "subtitles look
  incomplete" note on the movie page.
- Needs a re-bake + R2 publish (see `moviewords-status` memory for recipes).

## 2. Per-film word lookup (feature)

**Ask:** "how many times does *The Wolf of Wall Street* say fuck?" There's no
way to answer that on the site today:
- Movie page (`app/src/views/Movie.tsx`) shows top 25 / signature words; the
  baked `json/movie/<id>.json` only carries the **top 200** words (`top`),
  `top_all` (50) and `distinctive` (50).
- Trends shows the top **15** films per word (`json/trend/<word>.json` `top`).

**Idea:** a "find a word in this film" box on the movie page -> count, rate per
1k words, and rank among all films for that word (+ link to the word's trend).
Full per-film counts exist in `all/words_by_movie/data.parquet`; options are a
DuckDB-WASM range query (but see the `trends-mobile-slow-duckdb-engine` memory:
avoid making mobile pay the 35 MB WASM cold-boot) or pre-baking per-film full
word lists (size check needed - 51k films). Would also make a nice Reddit reply
tool. Do **after** #1, or it will surface the broken files more prominently.

## 3. MPAA ratings (analysis / possible follow-up post)

A commenter asked whether R/X-rated films are included. **Yes** - there's no
rating filter; it's every film with English subtitles in the corpus. But we
**don't have ratings**: `pipeline/scripts/fetch_tmdb_meta.py` requested
`append_to_response=credits,keywords`, and TMDB keeps certifications in the
separate `release_dates` block. (Also: `tmdb_meta.parquet` / the raw TMDB cache
are **not on this Mac** any more - only in the archive noted in memory.)

**Plan:** fetch `/movie/{tmdb_id}/release_dates` for the ~25k English-original
films (`TMDB_API_KEY` is in `.envrc`; ~10-20 min at TMDB's rate limit), take the
US certification. Caveat: that's the **current** US rating, not necessarily the
original one - many pre-1968 films are "NR" or re-rated later, so a by-rating
split is meaningful from ~1970.

**Payoffs:**
- Swearing over time split into G/PG, PG-13, R lines (PG-13 was created in
  1984 - its own story).
- Tests the hypothesis for the **2003-04 dip** in the chart (see below).
- Candidate second r/dataisbeautiful post (wait ~a week after the first).

**The 2003-04 dip, as far as the current data goes** ("fuck" per million words,
English-original films): ~940-1,100 in 1998-2002, **797 (2003), 736 (2004)**,
~1,030 by 2005. Explanations found:
- Documentaries jump from ~3% to ~8% of the corpus's films from 2003 (they swear
  less) - but excluding them the dip remains (861, 790), so it's not only that.
- Among popular films (>= 50k IMDb votes, ~90-100/yr), the share with **zero**
  "fuck" peaks at 57% / 56% in 2003-04 vs ~50% either side - consistent with the
  early-2000s PG-13 push, but unproven without ratings.
- Rates are driven by a few extremely sweary films, so years swing; 2002 is
  unusually high, exaggerating the drop.

## Regenerating the chart

`swearing-data.json` = English-original films (`movies.parquet`
`original_language = 'en'`), per release year, `sum(count)/sum(total_words) * 1e6`
over a centered 3-year window, years with < 100k corpus words dropped (same rule
as the site). Render: serve the repo root over HTTP (the page `fetch`es the JSON;
`file://` blocks that), open `docs/launch/swearing-chart.source.html` at
1600x1000 in Playwright, screenshot. Fonts load from `app/public/fonts`.
Palette = site series colors, validated with the dataviz skill's
`validate_palette.js` (CVD pair in the 6-8 band, OK with the direct labels).

## Related

- `docs/handoffs/2026-09-24-post-hn-sharing-strategy.md` - channel plan
  (r/movies, PassThePopcorn, etc. still unused)
- `docs/launch/hn-show-hn.md` - drafts (its Reddit/Bluesky sections predate the
  swearing chart)
- Comment watcher: `~/.local/hn-watch/` (HN + Reddit RSS + Bluesky -> Pushbullet;
  see the `hn-watcher` memory)
