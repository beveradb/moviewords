# Content-consensus subtitle selection - 2026-09-24/25

**Project:** moviewords   **Branch:** feat/sess-20260924-1632-content-consensus-selection   **Status:** data published to R2 + verified live; PR pending merge (pipeline-only, no app deploy)

## Summary

Andrew spotted Othello (1951) showing words from *O* (2001). An OPUS
subtitle folder holds one file per OpenSubtitles upload, and the size-based
pick often landed on an outlier. This PR chooses each film's file by
**content consensus**: fingerprint every candidate, gate out obvious junk,
take the most typical file of the largest group of agreeing texts. Recount +
rebake ran on a GCP VM and is live.

## How we got here

1. **Othello → a corpus sweep (2026-09-24 afternoon).** Compared each film's
   chosen file with its first alternate over HTTP ranges, then with its
   whole folder. ~350 films were clearly wrong. Batch 1 (8 films) went into
   PR #38 as blocklist lines. A ~400-line batch 2 was cancelled in favour of
   this structural fix.
2. **Study (100 films: 50 random + 50 known-bad).** Why folders have many
   files: re-syncs of the same text (PAL 0.959/1.043 speed ratios, offsets
   from different cuts), edits, hearing-impaired variants, exact duplicates
   (content cosine 0.97-1.0), independent translations (0.6-0.8), and
   outliers - DVD commentary tracks, wrong films, wrong languages, tag junk.
   Known-bad picks were the LARGEST file in 69% of cases. The folder medoid
   was genuine in ~all 100. OPUS itself picks one version per film for its
   bitexts (Lison & Tiedemann, LREC 2016).
3. **Calibration** (plan doc: `docs/superpowers/plans/2026-09-24-content-consensus-selection.md`):
   commentary tracks run 8-24 film-making words per 1k tokens (normal p99
   9.3) at 13-16 bytes/word (normal ~24). English-stopword share is 0.43+ for
   normal files and ~0.07 for wrong-language ones. OPUS's `<confidence>` is
   unreliable (1.0 on a German file).

## What changed

- `corpus_index`: size ranking is a pre-filter only; stores up to 12
  `candidates` (name + bytes) spread over it, replacing `alternates`.
- `consensus.py` (new): fingerprints (top-300 content words, stopword
  share, commentary rate, bytes/word); gates (commentary, not-english,
  sparse, tiny - relaxed if all fail, e.g. musicals); near-identical files
  (cos >= 0.98) form one **text**; groups rank by (agreeing texts at cos >=
  0.85, files, rank order); pick the median-length member; doubled-file
  guard.
- `counts`: per-film cache of per-file fingerprints; `FINGERPRINT_VERSION`
  (parser/tokenizer - refetch) vs `SELECTION_VERSION` (re-choose from cached
  fingerprints in ~2 min); `count --shard K/N`; `work/selection.parquet`.
- `subtitle_parser`: strips SSA `{\...}` blocks, mangled `font color=...`
  tags and `nbsp` (they were counted as words: chffffff, fad, pos).
- Blocklist: 11 stray files in Vinaya Vidheya Rama's majority-wrong folder.
- `upload_r2.sh`: `RCLONE_RETRIES=1` and an old-rclone warning.
  `docs/PIPELINE-RESTORE.md`: europe-north1 VM, local zip, sharded count,
  gotchas below.

## Results (64,633 films)

- 45,704 chosen by consensus, 17,435 single-file, 1,488 by rank order (no
  agreement). 896 commentary files rejected (307 were previously published),
  48 not-English (15 published).
- 32% of picks changed, but ~90% of those are the same content (a different
  upload of the same text). **~2,000 films changed content.** The most-voted
  were fixes: commentary replaced on Gladiator, The Lion King, Star Wars
  IV-VI/III/VII, The Martian, Spider-Man, Deadpool, Logan, Heat, Jaws,
  Aliens; wrong films replaced on An American Werewolf in London (was Bee
  Movie), Avatar (Hindi Medium), WALL·E, Metropolis 1927, Alice in Wonderland
  1951; wrong languages replaced on Philadelphia (Vietnamese), Raising
  Arizona, Inglourious Basterds.
- A v1 → v2 fix during review: Baahubali 2 had 3 identical uploads of
  another film outvoting genuine translations, so votes now count distinct
  texts (also fixed Spider 2002 carrying a Spider-Man file).
- Pre-1968 "fuck" audit (Andrew's request): 146 films before → 131 after;
  25 removed (Alice in Wonderland x45, The Wrong Man x12, Thoroughly Modern
  Millie, Return of the Fly...). 105 remain on the same file, 57 of them
  single-file folders (Sunrise 1927, Hollywood Revue of 1929) where
  consensus has nothing to vote with - a manual review list. CSVs:
  `~/Projects/beveradb/moviewords-mislabel-study-2026-09-24/pre1968-fuck-*.csv`.

## Publish (VM moviewords-pipeline-tmp, europe-north1-a, n2-highmem-8)

Bootstrap + local 34GB zip ~15 min; 8-shard recount ~25 min; derive 11+16
min; web rebuild 10+17 min; language + rating slices ~20 min; upload pass 1
~1.5h (see gotchas), passes 2-3 16 min; purged. Live check: Philadelphia,
Werewolf, Heat, Baahubali 2, Othello, Alice all serve the right words;
movies-index 64,579 (unchanged count).

## Gotchas

- `mw_vm_count.sh` deadlocked: `exec > >(tee log)` + bare `wait` waits on
  tee. Cost ~1h.
- The laptop-made cache tar carried 113k macOS `._*` files; derive choked
  on `tmdb/._tt*.json`.
- Debian's rclone 1.60 → R2 501s on every unchanged file; counted as errors,
  so the default 3 retries re-checked 770k files from a slow pd-standard
  disk. Killed after attempt 1 (whose changes were verified on R2).
- Single-file and majority-wrong folders are consensus's limits: the
  blocklist or the cross-film pair scan (`scan_mislabels.py`, widen its
  rare-word window) still apply.

## Open threads

- Manual review of the remaining pre-1968 "fuck" films, especially English
  single-file ones (Sunrise, Hollywood Revue, Lady Luck, Happy Go Lovely).
- `scan_mislabels.py` recall (rare-word window 2-20 misses common names)
  and its saturated stage-3 consensus threshold.
- `yyy`/OCR letter-spacing junk in some files (consensus avoids them where a
  folder has alternatives).
- VM: archive `moviewords-work-cache-2026-09-25` then delete.
