# Content-consensus subtitle selection - plan (2026-09-24)

## Why

A 100-film study (50 random + 50 known-bad films; data in
`~/Projects/beveradb/moviewords-mislabel-study-2026-09-24/`) found:

- An OPUS film folder holds one XML per OpenSubtitles upload. Most uploads are
  the same text re-synced to other video releases (PAL 25fps ratio 0.959 /
  1.043, offsets from different cuts), lightly edited, with or without
  hearing-impaired tags, or exact duplicates. Word counts barely differ
  between them (content-word cosine 0.97-1.0).
- Independent translations exist, often with names transliterated
  differently (arvind / aravind), and score 0.6-0.8.
- The harmful outliers are DVD/Blu-ray commentary tracks, wrong films
  (upload errors, same-title or remake mix-ups), wrong-language files,
  styling-tag junk and partial/lyrics-only files.
- Known-bad picks were the LARGEST file in 69% of cases. The most typical
  file of each folder was genuine in ~all 100 folders.

So a file chosen by content consensus is right almost everywhere, and size
ranking (PR #38) is only a pre-filter.

## Calibration (2026-09-24, current corpus)

| Signal | Normal files | Bad files |
|---|---|---|
| Film-making words / 1k tokens | p50 0.7, p99 9.3 | commentary 8-24 |
| Raw bytes / counted word | ~24 (p5 18) | commentary 13-16 |
| English-stopword share | p50 0.51, p1 0.43 | Vietnamese/Danish 0.07; Inglourious Basterds (genuine) 0.27 |
| OPUS `<confidence>` | unreliable: 1.0 on a German file | - |

In-band candidates per film: p50 2, p90 10, p99 31, max 182. 17.4k films
have 1 candidate, 15.5k have 2, and 31.8k have 3+. Capping the sample at 12
per film means 242k reads for a full recount.

## Design

1. **Parser** (`subtitle_parser`): strip SSA/ASS override blocks
   (`{\cHFFFFFF}`, `{\fad(..)}`, `{\an1\pos(..)}`), mangled font tags
   (`font color = "# 00ff00"`) and `nbsp`.
2. **Index** (`corpus_index`): keep `rank_candidates` as a pre-filter. Store
   `candidates` = up to `CONSENSUS_MAX_CANDIDATES` (12) files spread evenly
   over the ranked list, always including the rank-top, with byte sizes. This
   replaces `alternates`. `zip_name` stays as the rank-top.
3. **Selection** (new `consensus` module, pure functions):
   - Fingerprint each candidate: token total, bytes/word, stopword share,
     commentary rate, top-300 content-word vector.
   - Gates: not-English (stopword share < 0.25), commentary (rate >= 8 and
     bytes/word < 18), sparse (bytes/word > 60) and tiny (< 200 tokens). If
     every file fails, relax to the parseable files (e.g. musicals are sparse
     everywhere).
   - 3+ usable files: support = number of others at cosine >= 0.85. If the
     best-supported file has support >= 1, its cluster wins; otherwise fall
     back to rank order.
   - 2 usable files: if they agree, that is the cluster; otherwise rank order.
     1 usable file: take it.
   - Within the cluster, pick the member whose token total is closest to the
     cluster median, with rank order breaking ties. This rejects doubled and
     partial rips without special cases.
   - Keep the doubled-file guard (> 200 wpm with a 40-60% twin in the
     cluster).
4. **Count** (`counts`): fetch and fingerprint every candidate, choose, and
   store the full counts of the chosen file. The cache record keeps per-file
   fingerprints plus `SELECTION_VERSION`, so re-runs only fetch new
   candidates and a version bump forces a recount. Write `selection.parquet`
   (imdb_id, chosen, rank_top, candidates, usable, cluster, reason) for
   review.
5. **scan_mislabels**: read the chosen file from the count cache (unchanged).
   The cross-film pair check stays the tool for majority-wrong folders, and
   the blocklist stays for those.

## Validation before publish

- Unit tests for the parser, consensus and count cache.
- Full index + count on the real corpus (remote OPUS, ~242k reads).
- Compare against the current picks: how many change, with a random sample
  of changes read by eye. Check the known cases: Werewolf (Bee Movie), Heat /
  Logan / Deadpool (commentary), Philadelphia (Vietnamese), Othello, Avatar,
  Vinaya Vidheya Rama (majority-wrong, still blocklisted).
- Then derive + bake + publish (needs Andrew's go-ahead; ~1.5h upload).
