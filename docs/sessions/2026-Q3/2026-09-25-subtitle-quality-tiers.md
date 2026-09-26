# Subtitle quality tiers - 2026-09-25

**Project:** moviewords   **Branch:** feat/sess-20260925-1353-subtitle-data-quality   **Status:** done - PR #43 merged (7d247e9), data published + purged, prod verified, VM deleted; docs PR #44 (DATA-QUALITY.md, FAQ, handoff for parked follow-ups)

## Summary

Executed `docs/handoffs/2026-09-25-subtitle-data-quality.md`. Each film's
subtitle is now judged on quality as well as content consensus: auto-
captions, machine-translated English, wrong-film uploads and anachronistic
profanity are passed over when a clean file exists; when none does, the film
keeps its page with a "Subtitle quality: low" note but is left out of every
aggregate (Andrew's policy). Design, calibration and rejected ideas:
`docs/superpowers/plans/2026-09-25-subtitle-quality.md`.

## Results (live)

- 64,648 films counted; **532 tier low** (0.8%: 414 machine-translated,
  83 auto-captions, 33 anachronism); site totals now 64,046 all / 34,556
  English-original.
- 1,684 films got a better file; 896 live picks changed.
- Pre-1968 English-original strong-profanity canary: 56 -> 12 films (the
  genuine 1960s documentaries/underground films + 3 edge cases).
- Sunrise shows its own intertitles (pre-1930 floor); Lady Luck, The Secret
  of My Success 1965, The Legend of Nigger Charley 1972 fixed via blocklist.
- OCR repair (l'm, lt's, i'ii, aii...) in ~5% of files.

## How it went

1. Labelled data: the 39-film pre-1968 audit + ~2,700 fetched files.
   ASR is trivially separable by line shape. Back-translation defeated
   n-gram fluency and vocabulary-era scores; a function-word logistic model
   worked (CV AUC 0.97).
2. First full run (VM, fingerprint v2) + reading every bucket changed the
   rules (selection v3 -> v6): no hard gates (the "dropped" films were
   documentaries about film-making), style model for English-original only
   (translationese fools it), cast check relative-only (the lone-file rule
   hit narrated films), plus an anachronism flag the style model misses.
3. Bake + publish on the VM; upload 102 min (865k files).

## Decisions & rationale

- Policy (Andrew): a film whose only subtitle is low quality keeps its page
  with a note but is out of every aggregate; nothing is dropped.
- Style model judges English-original films only - on human translations of
  foreign films it reads translationese as MT (~40% precision).
- Cast check is relative-only; single-file wrong films go on the blocklist
  (lone-file rule hit narrated/unnamed-character films).
- No hard gates: "commentary-only" films were documentaries about film.
- Anachronism flag: strong profanity in pre-1965 English-original fiction;
  the 1965-68 underground/documentary hits are genuine.
- Follow-ups (silent films' TMDB, cross-film scan, grey zone, translated-film
  MT, faster upload) parked: each needs a full re-bake + ~1.7h upload, which
  Andrew didn't want now.

## Gotchas

- `bootstrap.sh` exited silently on a fresh image (pipefail on the rclone
  probe) - fixed; the env file needs `export`s.
- gcloud: use `--account=andrew.d.beveridge@gmail.com` for nomadkaraoke.
- Upload speed is per-request latency (R2 PUT ~70-100 ms, 64 in flight =
  ~300 files/s): disk, CPU and bandwidth were idle. Faster: more transfers
  (256+), one listing instead of three passes, or pack per-film/per-word
  JSONs into shards.
- Cache archive: `moviewords-work-cache-2026-09-25-fpv2.tar.zst` (use
  `scripts/vm/archive.sh` with a NAME - date-only names overwrite).

## After shipping

- Andrew checked the pre-1969 "fuck" trend (English only): the 4 films left
  are genuine - Primary (1960; "Well, fuck." at a vote count, plausible
  candid audio, unverifiable), Chelsea Girls (1966), Warrendale (1967) and
  Symbiopsychotaxiplasm: Take One (1968, crew arguing on camera; outside the
  "before 1968" canary). Kept.
- The whole story, written for readers (and the Reddit reply): 
  `docs/DATA-QUALITY.md`. FAQ, README, pipeline README and llms.txt updated;
  CLAUDE.md now says to run the audit before any publish.
- Upload analysis (Andrew asked why 102 min): 865k files, one HTTPS PUT
  each; the VM's disk read 0 MB/s (page cache), CPU 67% idle, 0.7 MB/s out -
  latency-bound at ~300 files/s with 64 transfers. Ideas in the follow-ups
  handoff.

## Related docs

- `docs/DATA-QUALITY.md` - the whole story for readers (share this one)
- `docs/superpowers/plans/2026-09-25-subtitle-quality.md` - design + calibration
- `docs/handoffs/2026-09-26-subtitle-quality-followups.md` - parked work
- `docs/sessions/2026-Q3/2026-09-25-content-consensus-selection.md` - PR #41
- Study data: `~/Projects/beveradb/moviewords-quality-study-2026-09-25/`

## Open threads

All parked in `docs/handoffs/2026-09-26-subtitle-quality-followups.md`
(each needs a full re-bake + upload, so do them together).


- 17 newly admitted silent-era films aren't live: no TMDB record (enrich
  never ran for them) - needs enrich + credits + posters + a re-bake.
- Single-file wrong films: a cross-film "whose cast does it name?" scan.
- MT detection for translated films needs its own labelled model.
- ~230 English-original films in the MT grey zone (0.4-0.8): review list in
  `scripts/audit_quality.py`.
- Upload speed ideas above.
