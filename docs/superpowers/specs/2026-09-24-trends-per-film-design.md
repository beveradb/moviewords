# Trends: "per film" view - design

**Date:** 2026-09-24   **Status:** approved (brainstorm), ready for plan
**Why:** a Reddit commenter asked "what's the average fucks per movie?" - the
site can only answer in uses per million words. Make "average uses per film"
a first-class, linkable view on the Trends page for any word.

## Scope

In: a per-film denominator for the Trends chart, a URL-persisted toggle, a
one-line per-word summary, the tiny bake file that makes it possible.
Out (follow-up, needs a full trend re-bake): "% of films that say it" and
median uses per film.

## Data: `json/year-films.json`

- `{ "<year>": <number of films released that year> }`, one file beside every
  `year-totals.json`: global `all/json/year-films.json` plus each language
  slice `all/lang/<code>/json/year-films.json` (35 files).
- Source: the slice's `movies` table (`SELECT year, count(*) ... GROUP BY year`),
  i.e. the same films whose words make up that slice's `word_year`.
- Built by a new `write_year_films(con)` in `pipeline/scripts/rebuild_web_data.py`,
  called from `stage_trends` (so future bakes include it) **and** exposed as its
  own stage `yearfilms`, so today we can bake + upload just these 35 files
  without regenerating the ~485k per-word trend JSONs.
- Per-language: run through the existing slice machinery
  (`bake_all_languages.py` / `build_lang_slice.py`) with `--stage yearfilms`,
  or equivalent - the plan verifies how slices set `IN/OUT` and reuses it.
- Upload: `upload_r2.sh` must include `json/year-films.json` at the global and
  `lang/*/json/` levels (it root-anchors patterns - check the rule list that
  already covers `year-totals.json`). Same cache headers as `year-totals.json`.

## Frontend

**Denominator.** `toSeries` currently divides by `totals` (words/year) x 1e6.
Generalise it with a mode: `'words'` (unchanged default) or `'films'`, where
`y = count / films.get(year)`. Year trimming (`MIN_YEAR_WORDS` on word totals)
is unchanged in both modes, so the same years are plotted either way.

**Loading.** `bakedYearFilms()` mirrors `bakedYearTotals()`: session-cached,
0 languages -> global file, 1+ -> fetch each selected language's file and sum
per year with the existing `mergeYearTotals`. Fetched alongside the chart data
whenever words are charted or per-film mode is on (it's ~1 KB and feeds the
summary line in both modes). If it fails: per-film mode shows the existing
error UI and the summary line is omitted - no engine fallback needed (the
engine path can't produce it cheaply either).

**Small values.** Per-film values are often < 1 (e.g. "swell" ~0.05/film), but
`LineChart` floors `yMax` at 1 and rounds ticks/tooltips to 1 decimal. Fix:
floor only at > 0, and format chart values with 2 significant decimals below 1.
Featured charts (no `?w=`) support the toggle too - same `toSeries` call.

**Toggle.** Segmented control above the chart: "Per million words | Per film".
State lives in the URL: `per=film` present -> per-film, absent -> default, so
`#/trends?w=fuck&per=film` is linkable. Adding/removing words preserves `per`.
Y-axis label and the caption under the chart switch with the mode.

**Per-word summary** (under the chart, one line per charted word, per-film
mode *and* default mode - it's the direct answer to "how many per film"):
`"{word}": {latest} uses per film in {decade}s films (all years: {overall})`
- `latest` = sum(count) / sum(films) over plotted years in the decade of the
  latest plotted year; `overall` = the same over all plotted years.
- Numbers via `n()`: 1 decimal at >= 1, 2 decimals below 1, "<0.01" when
  non-zero and smaller, "0" for zero. Words with no data are already listed as
  missing. Shown for user-charted words (not the featured chart).

**i18n.** New `trends.*` keys in `en.json` (toggle labels, per-film axis label
+ caption, summary line); translated by the pre-commit hook / `npm run translate`.

## Known caveat

~4% of English-language films have truncated/mismatched subtitle files (see
`docs/handoffs/2026-09-24-launch-feedback-followups.md` #1). They count as
films but contribute few words, so per-film averages are slightly low (a few
%). Fixed at source by that follow-up, not here.

## Testing

- Unit (vitest): `toSeries` per-film mode (values, trimming identical to words
  mode); decade summary maths (latest-decade + overall, sparse/missing years);
  `per` param parse/preserve helper; year-films merge across languages.
- Pipeline (pytest): `write_year_films` output for a tiny fixture DB.
- Manual/Playwright: `#/trends?w=fuck&per=film` on the deployed site, with and
  without a language filter; mobile width.

## Ship

Bake `yearfilms` for global + 34 languages -> upload those files -> verify 200s
-> merge PR (auto-deploys the app). Data must be live before the app, or
per-film mode errors until it is.
