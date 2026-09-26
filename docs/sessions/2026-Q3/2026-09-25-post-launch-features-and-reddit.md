# Post-launch: Reddit/Bluesky launch, per-film + MPAA + word-explorer features, data refresh - 2026-09-24/25

**Project:** moviewords   **Branch/commit:** main @ 5998d4a (PRs #37, #39, #40, #45 merged by this session)   **Status:** done - all shipped + prod-verified; Reddit thread answered

## Summary

The Show HN (item 49829886) was auto-killed by HN's spam filter within minutes
(dead, score 1, account karma 2). Andrew emailed hn@ycombinator.com; we moved to
r/dataisbeautiful + Bluesky with a single chart ("How Hollywood learned to swear",
1968 Hays Code line). The Reddit post did well (429 points, 97%, 82+ comments,
~102k views) and its questions drove three shipped features, a production data
fix, and a data-quality write-up. Parallel sessions fixed subtitle selection
(#38, #41, #43); this session consumed their results for Reddit replies and a
redrawn chart.

## What changed

**Launch & monitoring**
- Comment watcher: launchd job `com.beveradb.hn-watch` runs
  `~/.local/hn-watch/hn_watch.py` every 5 min - Pushbullet push on new HN
  comments / dead-alive change (item 49829886), Reddit thread comments (via the
  thread's `.rss`; JSON API 403s without OAuth; skips u/andrewthecoder) and
  Bluesky replies (public AppView `getPostThread`). **Still running** - stop with
  `launchctl bootout gui/$(id -u)/com.beveradb.hn-watch`. Memory: `hn-watcher`.
- Reddit post: https://www.reddit.com/r/dataisbeautiful/comments/1wp34ek/
  (image post + required [OC] source comment). Bluesky:
  https://bsky.app/profile/did:plc:qs7vxexysirqimpz25vnlx4q/post/3mwbiah4mk22e
  (#FilmSky #dataviz, alt text).
- Chart: `docs/launch/swearing-chart.{png,source.html}` + `swearing-data.json`
  (HTML/SVG in site fonts -> Playwright screenshot; English-original only).

**PR #37 - Trends "per film" view** (`#/trends?w=fuck&per=film`): toggle
(per million words | per film) in the URL, per-word summary line ("N uses per
film in 2020s films (all years: M)"), LineChart handles values < 1. Data: new
`json/year-films.json` (films per year) for global + 34 language slices
(`rebuild_web_data.py` `write_year_films` / `--stage yearfilms`).

**Prod data fix (no PR):** a parallel session republished the 64.6k corpus
(from a branch predating year-films) -> live `year-totals` 64.6k vs
`year-films` 51.6k, per-film numbers ~25% high. Rebuilt the 35 year-films files
from that session's inputs, uploaded, purged the CDN. (Now structurally fixed:
`pipeline/scripts/vm/bake.sh` rebuilds year-films, rating slices and word lists.)

**PR #39 - MPAA rating filter** (`#/trends?w=shit&rating=pg`): select
All | G | PG | PG-13 | R & NC-17/X (NC-17/X folded into R - only ~5 films/yr),
disabled under a language filter, inactive on the featured chart, charts start
in 1968 (pre-1968 films only carry re-release ratings - 25 are even "PG-13").
`pipeline/scripts/fetch_ratings.py` (TMDB `/find` + `/release_dates`, earliest
theatrical MPAA cert, per-film cache in main checkout `data/work/tmdb_release/`,
64,579 films, ~20k rated) -> `ratings.parquet`; `build_rating_slice.py` +
`bake_all_ratings.py` -> `all/rating/{g,pg,pg13,r}/json/`. No SQL-engine fallback
for rated views. Finding for Reddit: PG films said "shit" ~300-400/M in the
70s-80s, collapsing to ~50-100 by the early 90s after PG-13.

**PR #40 - film-page word explorer** (`#/movie/tt0064115?q=shit`): every word a
film says (`json/words/<imdb_id>.json` = `[[word, count, films]]`, 64,579 files,
`rebuild_web_data.py --stage words`), linkable search (history.replaceState),
stretched spellings ("shit" finds "shiiiit" - 3+ letter run, letters only),
sortable 50/page list, "only in this film", singular "the only film that says it".

**PR #45 - docs:** `docs/DATA-QUALITY.md` consistent "pre-1968" canary wording
(56 = films with any strong profanity; 39 = the "fuck" subset read line by
line) + a "launch chart, redrawn" section:
`docs/launch/swearing-chart-families-2026-09-25.{png,source.html}` + data -
English-original, low-quality films excluded, **word families** (fuck* =
fuck, fucking, fucked, motherfucker...). Launch-feedback handoff #1-#3 marked done.

**Reddit/Bluesky replies** (all drafted in Playwright, reviewed + posted by
Andrew): Hays/2005-dip explanations, rating filter, per-film link, Butch
Cassidy "shiiiit" (explorer link), R-rated plateau, Gone with the Wind "damn"
x1, Othello/Loving You corrections, Alice in Wonderland fixed, full pre-1968
list with the redrawn chart, source-comment EDIT linking DATA-QUALITY.md.

## Decisions & rationale
- Rated charts start in 1968; NC-17/X merged into R - otherwise unchartable/biased.
- Rating uses the original theatrical certification (not "current") - matches
  the question being asked; copy says so.
- Word families for the redrawn chart - single "fuck" is only ~42% of its
  family vs ~86% for "shit", so single words distort the gap between lines.
- Per-film data baked as tiny files instead of loading the 1.8 MB movies index.
- Plan-mandated code duplication (fetch helpers, slice/bake loops, streaming
  loop, sidecar loaders) left as follow-ups (handoff #5) - Andrew didn't object.

## Learnings / gotchas
- HN silently kills low-karma self-promo posts; check `hacker-news.firebaseio.com
  /v0/item/<id>.json` for `"dead": true`; fix = email hn@ycombinator.com.
- Any corpus republish must rebuild year-films, rating slices and word lists
  (memory `rebake-coupled-data`; vm/bake.sh now does it).
- `movies.parquet` already has a `rating` column (IMDb score) - name MPAA joins explicitly.
- Reddit rich editor: `fill()` on the contenteditable is reliable; `execCommand`
  insertParagraph/insertText glued text onto an existing link. Cancel opens a
  discard dialog. Reddit's image uploader ignores Playwright's file chooser.
- zsh doesn't word-split `$var` (`set -- $pair` broke a loop).
- Reddit JSON/RSS rate-limit back-to-back requests (429); 5-min polling is fine.
- The Playwright MCP can only write files under the main checkout
  (`.playwright-mcp/`), not other worktrees.

## Open threads & next steps
- **New data issues (prompt handed to another session):** silent films with
  swearing - 7th Heaven (1927, shit x4) and Dog Star Man (1964, shit x4); ~10
  unverified single "shit"s in 1927-59 studio films (Passage to Marseille, Angel
  and the Badman, Lone Star...); extend the audit canary to the whole
  strong-profanity family. Andrew told Reddit these are "still being checked" -
  post a follow-up in OKStamped's thread when resolved.
- Parked subtitle-quality work: `docs/handoffs/2026-09-26-subtitle-quality-followups.md`.
- Launch-feedback handoff #4 (pre-1968 MPAA ratings) + #5 (duplication cleanup,
  explorer polish: trend links for rare words, a11y, docs).
- HN: mods emailed; watcher will push if the post is revived. Consider a Show HN
  repost in ~1-2 weeks (HN allows one).
- Optional: US-produced-only swearing chart (tightest Hays Code framing); a
  second r/dataisbeautiful post (e.g. PG-vs-PG-13) after ~a week.
- Housekeeping: `pipeline/webdata-rating/` (2.1 GB, git-excluded scratch: rating
  + word-list bakes, symlinks into a deleted worktree) can be deleted; the
  ratings cache `data/work/tmdb_release/` (64,579 files) should be kept (or
  archived) for incremental re-fetches.

## Related docs
- `docs/DATA-QUALITY.md`; `docs/handoffs/2026-09-24-launch-feedback-followups.md`;
  `docs/handoffs/2026-09-26-subtitle-quality-followups.md`
- Specs/plans: `docs/superpowers/specs|plans/2026-09-24-{trends-per-film,mpaa-rating-filter,film-word-explorer}*`
- Parallel sessions: `docs/sessions/2026-Q3/2026-09-24-subtitle-file-selection.md`,
  `2026-09-25-content-consensus-selection.md`, `2026-09-25-subtitle-quality-tiers.md`
- Memories: `hn-watcher`, `rebake-coupled-data`
