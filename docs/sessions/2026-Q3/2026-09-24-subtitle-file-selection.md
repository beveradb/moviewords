# Subtitle file selection fix: +12,959 films, featurette/double/garbage picks — 2026-09-24

**Project:** moviewords   **Branch/commit:** main @ 8abb664 (PR #38 squash-merged; worktree + branch cleaned up)   **Status:** done - data live on R2, app deployed, prod verified

## Summary

Executed item #1 of `docs/handoffs/2026-09-24-launch-feedback-followups.md`
(bad/truncated subtitle files). The cause turned out to be much bigger than
a few bad files. `corpus_index.select_best` estimated a candidate's word
count as raw XML bytes / 8, but the real ratio is ~24.5 (median over the
51.7k chosen files; p5-p95 18-33). So the "250 words/min" cap really meant
~80 wpm and rejected every full-length rip of talky films:

- Some films fell back to the only file under the cap: a featurette (The
  Wolf of Wall Street: 2,920 words → now 22,636, "fucking" x349) or a
  partial/forced track (Superbad, Spider-Man: No Way Home).
- **12,959 curated films had nothing left and were silently dropped**:
  GoodFellas, Good Will Hunting, Toy Story, Gone Girl, Oppenheimer, 12
  Angry Men, The Social Network, Knives Out, Mean Girls... (311 of them had
  100k+ IMDb votes). That also biased the aggregates against talky films.

Corpus now: **35,066 English-original (was 25,515) / 64,579 all films
(was 51,624)**, 469M words (was 328M).

## New selection rule (pipeline)

`corpus_index.rank_candidates` (config constants in `config.py`):
1. Keep files in a calibrated band: 5-400 estimated wpm at 24.5 bytes/word.
2. With 4+ in-band files, drop anything > 1.5x the upper-quartile size.
   Doubled files can come in PAIRS that peer each other (Forrest Gump: 468KB
   + 439KB doubles over a ~25-file ~250KB cluster).
3. Rank files with a size peer (another file within 1.25x) first, then
   peerless ones, largest-first in each group. Real rips cluster; featurettes
   and doubles are loners. This survives directories where forced-only
   tracks are the majority (No Way Home: 50 forced + 18 full), which is why
   an earlier median-based guard was dropped.
4. The index stores the next 3 as `alternates`.

`counts.build` verifies each top pick at count time:
- **> 60 bytes/word** (sparse): count the alternates and keep the wordiest.
  Catches mis-encoded files (Pirates: Dead Man's Chest's pick was half
  byte-swapped UTF-16, 712 words). Musicals keep their pick, since every
  file is sparse because lyrics are stripped.
- **> 200 words/min**: an alternate holding 40-60% of the words means the
  pick is a doubled file (Dragon Seed, Undercurrent, Get Shorty).
- A fetch failure fails the film (uncached, retried next run). It never
  falls back, so a network blip can't cache a worse file.
- The cache record's `zip_name` is the file actually counted. `indexed_as`
  = the index's pick when an alternate won, and it's reused only while that
  alternate is still in the index's alternates (blocklisting takes effect).

## No VM: remote OPUS zip

`opus_zip.RemoteZip` reads the published 34GB OPUS zip over HTTP range
requests: the central directory takes ~1.6 min, then one ranged GET per
member (per-thread sessions). `index`, `count` and `scan_mislabels
--adjudicate` use it automatically when `data/raw/opus_en.zip` is absent.
`count --workers 16` re-counted ~22k films in 14 min from the laptop.
Restore the work cache from `r2:moviewords-pipeline-cache` first (see
`docs/PIPELINE-RESTORE.md`, now updated).

## Mislabel blocklist (+10 films)

- scan_mislabels --adjudicate: The Place Promised in Our Early Days (a
  Naruto sub) and The Visitors II (The Visitors 1993). Both were newly
  surfaced because the new ranking picked a larger mis-filed upload.
- Batch 1 from a parallel session (moviewords-73) doing a content sweep:
  Othello 1951 (O 2001), The Last Airbender (Prince of Persia), Robin Hood
  2010 (LOTR RotK), DBZ Broly Second Coming, Vinaya Vidheya Rama (13
  Neevevaro copies outranked the genuine files), Zatoichi and the Chest of
  Gold, Battles Without Honor and Humanity, Haunting Me. A ~400-film second
  batch was CANCELLED in favour of a structural follow-up (below).
- scan_mislabels' consensus threshold (0.8) sits at the stopword floor, so
  every pair comes back "manual review". Read the per-file tables instead.

## Bake + publish recipe used (local, ~2.5h wall clock incl. waits)

1. Restore `moviewords-work-cache-2026-09-15.tar.zst` into the worktree's
   `data/work/` (the tar needs `zstd -dc | tar -x`; `tar -I zstd` broke).
2. `cli index` → `cli count --workers 16` → `cli enrich` (12,958 new TMDB
   lookups, ~45 min serial) → `scan_mislabels [--adjudicate]`.
3. `cli derive --corpus en|all` (5 + 8 min), `build_movies_index.py` x2.
4. `webdata/in` = symlinks to `data/out` parquets + copied signature JSONs.
   Then `rebuild_web_data.py --corpus en|all` + `bake_all_languages.py`
   (~30 min total).
5. Posters: symlinked the main clone's `data/out/posters`, then
   `fetch_posters.py` (now reads the all-films parquet) fetched + encoded
   12,943 new. Blurbs: served a movies-index of only the 12,969 films missing
   a blurb on localhost and ran `fetch_tmdb_meta.py --stage fetch
   --data-base http://localhost:8765`.
6. Stage derive outputs into `webdata/out` (movies/word_year/words_by_*
   parquets, movies-index, wordlists, word_year_lang), then `upload_r2.sh`
   with `POSTERS_DIR=<real path>` (rclone doesn't follow the symlink) and
   `RCLONE_TRANSFERS=64 RCLONE_CHECKERS=64`. At the default 4 transfers the
   ~680k small JSONs would take ~14h; at 64 it's ~1-2h.

## Numbers worth keeping

- Launch swearing chart (`docs/launch/swearing-data.json`) recomputed on the
  new corpus: same shape, individual points ±10-15% (e.g. "fuck" 2000:
  952 → 1,067 per million). The posted PNG was not regenerated.
- Residual < 30 wpm English films are genuinely quiet (silents, A Quiet
  Place, John Wick, Apocalypto) or musicals, so the handoff's "subtitles
  look incomplete" UI note was not built.
- 11 films fail to parse (no usable alternate); 43 have no TMDB match.

## Shipped + verified (2026-09-24 evening)

- R2 publish finished ~19:25 UTC with a zone purge. PR #38 merged at 19:30
  (8abb664), and the deploy workflow went green in 33s.
- Prod checks: moviewords.org HTML says "64,579 films" and llms.txt says
  "~65,000". The WoWS movie page renders 22,636 words / 126 wpm with real
  signature words (jordan, donnie, belfort, stratton, ludes). Othello 1951
  serves thou/cassio. GoodFellas (new) has its AVIF poster (1y immutable).
  The all-films movies-index has 64,579 entries.
- Interleaving check: PR #37 (Trends per-film view, other session) added a
  `json/year-films.json` bake that my branch predates. The live
  `all/json/year-films.json` sums to 64,579, i.e. it was baked AFTER my
  parquets went live, so there's no stale denominator. The flat en
  `json/year-films.json` 404s but the app never requests it (no-language =
  `all/`, languages = `all/lang/<code>/`).
- Merged `upload_r2.sh` = my 64-transfer defaults + #37's year-films and
  #39's rating-slice filter rules (GitHub combined them cleanly).

## Open threads

- **Follow-up PR (moviewords-73 session, approved by Andrew):** content-
  consensus selection. It clusters each folder's candidates by content-word
  cosine and picks the most typical file of the largest cluster; 1-2 file
  folders get a commentary-track detector + langid + tag-junk rate. A
  100-film study found the remaining bad picks are mostly the LARGEST file
  in big folders: DVD commentary tracks (Heat, Logan, Deadpool...), wrong
  films, junk. So size-based ranking (this PR) is a stepping stone. It also
  adds a parser fix for {\pos}/<font>/nbsp styling tags.
- `yyy`/`yyyi` encoding-junk tokens leak from some files (parser encoding
  bug; these make Match Point / Just Like Heaven look like duplicates).
- Old-pipeline cache records skip the count-time checks unless invalidated.
  This run invalidated the sparse (> 60 B/w) and fast (> 200 wpm) ones by
  hand; a future full recount makes that moot.
- `tmdb_meta.parquet` was not rebuilt (the local tmdb_meta cache only has
  the new films); it has no app consumer.
- (done) grown `data/work` cache re-archived as `moviewords-work-cache-2026-09-24.tar.zst` (787MB); the 2026-09-15 archive is kept alongside.
- Handoff item #3 (MPAA ratings) shipped separately as PR #39 (Trends rating
  filter, other session). Item #2 (a "find a word in this film" box on the
  movie page) is still open as far as this session knows. #37's per-film
  Trends view is related but not the same thing.
- Future publishes: the next full re-bake must include #37/#39's new outputs
  (year-films.json, all/rating/*). Run the current main's
  rebuild_web_data.py + bake_all_ratings.py, not an older branch's.
