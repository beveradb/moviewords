# "Shit"-family audit, silent films, cast scan, faster upload - 2026-09-25/26

**Project:** moviewords   **Branch:** feat/sess-20260925-2151-shit-family-audit   **Status:** done - PR #47 merged (600e8e2), data published + purged, prod verified, VM deleted

## Summary

A Reddit question led to a live-data query for the "shit" family in
pre-1968 English-original films. It returned 32 films, including a 1927
silent film. The round-3 anachronism rule only knew fuck/cunt. Every hit
was read in context against the film's other uploads
(`docs/audits/2026-09-25-pre1968-shit-family-verdicts.csv`): 11 genuine,
4 plausible, 4 transcription slips, 11 mishearings (mostly modern punctuated
speech-recognition uploads), 2 not the film. Bundled with the parked
follow-ups #1, #2 and #5 into one re-bake. Write-up for readers:
`docs/DATA-QUALITY.md`, round 4.

## What changed

- `quality.STRONG_PROFANITY_RE`: fuck/cunt any form + the English forms of
  shit (explicit suffix list). SELECTION_VERSION 8. v7 used a `^shit`
  prefix, which flagged romanised Japanese (shitai, shitsurei) in 3 films.
  Reading the re-choose diff caught it before publishing.
- `profanity_verified.txt` + `counts.load_profanity_verified`: The
  Connection and The Exiles (1961 dramas, genuine) are exempt. The flag is in
  the film key, so adding a film re-chooses it.
- Blocklist +22 files: 5 silent/wordless films whose only file is another
  film or a commentary track, The Power of the Press 1928 (the 1943 film
  beat the intertitles), Invasion of the Star Creatures ("shitty-shallying"),
  and 10 wrong films from the cast scan (Vijeta: 3 Viy uploads outvoted the
  genuine file).
- `scripts/scan_cast_crossfilm.py` (handoff #2): files naming 3+
  distinctive (<= 3 cast lists, zipf < 3) cast tokens of another film and
  none of their own. 19 hits, 10 wrong, 9 legitimately shared (same play,
  re-cut, alternate-title duplicates).
- `audit_quality.py`: the profanity canary uses the pipeline regex and lists
  the words, verified films are marked, and there's a new silent-era
  talkie-rate canary (pre-1928, > 45 wpm).
- Handoff #1: enrich + credits for the 17 silent-era films (all found); 16
  posters fetched + AVIF-encoded from the laptop and uploaded (Shattered 1921
  has none).
- Handoff #5: `upload_r2.sh` at 512 transfers.

## Results (live)

- 64,040 films (all) / 34,535 English-original; 542 low-tier in all (was
  532); 13 films removed (no genuine file); 17 silent films added.
- Live pre-1968 "shit" family: 32 -> 15 films, all genuine or plausible.
  Before 1965: only Primary (doc) + the 2 verified dramas.
- Upload: **7 min** (was 102). Common trend files were really rewritten.

## Decisions & rationale

- A word-rate rule for silent films was rejected: wordy genuine intertitles
  (Great White Silence, Orochi: 63 wpm) outrun 7th Heaven's wrong file (59).
  Blocklist + audit canary instead.
- Lone wrong-film files are blocklisted (the film leaves the site) rather
  than tiered low: a page of another film's words with a note would still
  be inaccurate data.
- Single-file mishearings go to tier low, consistent with the fuck rule
  (Andrew's policy: never show inaccurate data).
- Upload benchmark (20k 4KB files, laptop -> R2): rclone 64 = 200/s, 256 =
  540/s, 512 = 780/s, 1024 no faster; s5cmd 256 = 380/s; `--fast-list` is
  slower (sequential listing). No per-bucket R2 write limit (1 write/s per
  key only). The Worker-unpacks-tar idea wasn't tested: MOVIEWORDS_CF_TOKEN
  lacks Workers Scripts: Edit (wrangler deploy 403s on /secrets).

## Gotchas

- zsh doesn't word-split `$G`: gcloud's "no valid credentials" error was a
  single string argument `--account=... --project=...`.
- The first scp to a fresh VM can fail with the same misleading error; retry.
- Cached choices survive a regex fix unless SELECTION_VERSION is bumped.
- `pytest` collection fails on `test_translate_helpers.py` without the i18n
  deps (`google`); pre-existing, run with `--ignore`.

## Open threads

- Post the Reddit follow-up in OKStamped's thread (Andrew posts). Draft:
  "Checked them all: every pre-1960 "shit" was a subtitle error -
  transcription slips (one upload of Passage to Marseille has "SHIT." where
  three others have "Hi, Grand-Père"), mishearings ("eating bird shit" =
  bird seed), and a 1927 silent film whose only subtitle file was a modern
  gymnastics drama. Fixed and republished; the earliest genuine ones are
  1960s independents and documentaries, like The Connection (1961), which
  New York's censors banned over its heroin slang."
- Handoff #3 (grey zone) and #4 (MT in translated films) remain parked.
- Punctuated speech-recognition uploads: mostly accurate, occasional
  mishearings; no detector yet (profanity catches only the swearing ones).
- Worker-based bulk upload: needs a token with Workers Scripts: Edit.
- Cache: `r2:moviewords-pipeline-cache/moviewords-work-cache-2026-09-26-sel8.tar.zst`.
