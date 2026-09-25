# Content-consensus subtitle selection - 2026-09-24/25

**Project:** moviewords   **Branch:** feat/sess-20260924-1632-content-consensus-selection   **Status:** done - PR #41 merged (f0e4d50), data live + purged, VM deleted; follow-up handoff written

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

## After merge (2026-09-25)

- PR #41 squash-merged (f0e4d50) after an agent code review. The one
  finding (cache reuse ignored runtime changes) was fixed in 61071ba.
  CodeRabbit isn't installed on this repo.
- The grown cache is archived as `r2:moviewords-pipeline-cache/moviewords-work-cache-2026-09-25.tar.zst`
  (940MB, verified), and VM `moviewords-pipeline-tmp` is deleted.
- **All 39 English-original pre-1968 films with "fuck" were read line by
  line** (`~/Projects/beveradb/moviewords-mislabel-study-2026-09-24/pre1968-en-fuck-{lines.txt,verdicts.csv}`):
  only ~7 are genuine (1960s docs/underground: Portrait of Jason, Warrendale,
  Titicut Follies, Dont Look Back, Chelsea Girls, David Holzman's Diary, My
  Hustler) and 3 uncertain. 18 are **back-translated English** (right film,
  machine-translated from another language: "Fuck the cow yellow"), 7 are
  **auto-captions** (unpunctuated ASR, misheard words), 2 transcriber
  guesses, and 2 **wrong films**:
  - **Sunrise 1927:** the silent film's genuine intertitle files fall below
    the index's 5 wpm floor.
  - **Lady Luck 1946:** 2 identical wrong copies win the "more files"
    tie-break.
- Andrew's bar: **never show inaccurate data.** A thorough handoff for a
  fresh session covers every failure mode, plus detection ideas, policy
  questions, and the VM playbook: `docs/handoffs/2026-09-25-subtitle-data-quality.md`.
- The VM scripts that worked are now in the repo, with the deadlock/rclone/
  `._*` fixes: `pipeline/scripts/vm/{bootstrap,count,bake,upload}.sh`.

## Open threads

- **Next session: `docs/handoffs/2026-09-25-subtitle-data-quality.md`** -
  back-translated and ASR subtitles, the relaxation leak (a film whose only
  file is commentary or other-language still gets published), the silent-
  film floor (Sunrise), duplicate-copy tie-breaks (Lady Luck), TMDB cast-name
  validation, OCR/junk, and a repeatable canary audit. Ask Andrew:
  exclude vs flag.
- Live now and known wrong: Sunrise (tt0018455), Lady Luck (tt0038680).
- The next `count` re-chooses every film once (records lack
  `selection.runtime_minutes`); it's ~2 min and needs no reads.
