# Handoff: subtitle-quality follow-ups (parked 2026-09-25)

**For:** a session that can afford a full re-bake + re-upload (~2.5h on the
VM, ~$3). None of these takes effect without one, so do them together.
Background: `docs/sessions/2026-Q3/2026-09-25-subtitle-quality-tiers.md`,
`docs/superpowers/plans/2026-09-25-subtitle-quality.md`.

## Start here

- Restore `r2:moviewords-pipeline-cache/moviewords-work-cache-2026-09-26-sel8.tar.zst`
  (fingerprint v2 + selection v8, the 17 silent films enriched; bootstrap.sh's
  default; a SELECTION_VERSION bump re-chooses in
  ~2 min, locally or via `pipeline/scripts/vm/rechoose.sh`).
- Publish recipe: `pipeline/scripts/vm/{bootstrap,rechoose,bake,upload}.sh`.

## 1. 17 silent-era films aren't live (need enrich) - DONE 2026-09-26

The pre-1930 index floor admitted 17 films (Man with a Movie Camera, The
Last Laugh, Go West, Les Vampires, Asphalt, The Golem 1914...), but `enrich`
never ran for them, so derive drops them (no TMDB record). Run `cli enrich`
+ `cli credits` for them before the re-bake, then `fetch_posters.py` (+
AVIF encode) and upload their posters.

## 2. Cross-film cast scan (single-upload wrong films) - DONE 2026-09-26

Consensus and the relative cast rule can't see a wrong film that is the
folder's only file. Scan: for each chosen file, which film's TMDB cast does
its content vector (`fp["vec"]`) name? Flag files naming 3+ distinctive cast
tokens of another film and none of their own; read the hits; blocklist the
confirmed ones (and consider it as a selection rule if precise). Cast lists:
`work/tmdb_credits/`; `quality.cast_tokens`. The rejected lone-file rule
(names none of its own cast) hit narrated/unnamed-character films - naming
*another* film's cast is the missing evidence.

Done in the "shit"-family round (`docs/DATA-QUALITY.md`, round 4): enrich +
credits fetched all 17 (posters fetched from the laptop);
`scripts/scan_cast_crossfilm.py` found 19 hits, 10 wrong films blocklisted;
`upload_r2.sh` defaults to 512 transfers (~780 files/s measured vs ~200 at
64). A temporary Worker unpacking tar shards into R2 via a binding was not
tried: `MOVIEWORDS_CF_TOKEN` lacks Workers Scripts: Edit.

## 3. Grey zone review (~230 English-original films, MT score 0.4-0.8)

`scripts/audit_quality.py` lists them. Read and label (a sample was ~1 in 4
machine-translated: Zombex, Evilution, 100 Bloody Acres), add the labels to
the training set and retrain (round 3); the study scripts are in
`~/Projects/beveradb/moviewords-quality-study-2026-09-25/` (`train_bt.py`,
`bt_extra.txt`, `bt_notbt.txt`, `show.py`).

## 4. Machine translation in translated films (uncertain payoff)

The style model can't separate human translations of foreign films from MT
(translationese); it only judges English-original films. A separate model
needs labelled foreign human-vs-MT files; candidate features beyond style:
source-language debris tokens, glued words, " ," spacing, Greek ";" question
marks. Time-box it; ship only at English-model-like precision.

## 5. Faster upload - DONE 2026-09-26 (512 transfers)

The upload is latency-bound (~300 files/s at 64 transfers; disk, CPU and
bandwidth idle). Try `RCLONE_TRANSFERS=256 RCLONE_CHECKERS=256`, and one
listing instead of three passes (per-path Cache-Control). Structural: pack
per-film / per-word JSONs into shards (~800k of the 865k files).
