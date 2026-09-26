# Handoff: subtitle data quality - never show inaccurate data

> **DONE 2026-09-25 (PR #43).** Outcome: `docs/DATA-QUALITY.md` and
> `docs/sessions/2026-Q3/2026-09-25-subtitle-quality-tiers.md`; parked
> follow-ups in `docs/handoffs/2026-09-26-subtitle-quality-followups.md`.

**Created:** 2026-09-25   **For:** a fresh Claude session   **Priority:** high - data correctness is the site's credibility

## The goal

Andrew's bar: **the site must never show something inaccurate.** People
drill into the data (movie pages, the every-word explorer, Trends per-film
views, superlatives, rating/language slices), and a 1927 silent film that
says "fuck" five times is instantly visible and undermines trust in all of
it. Prefer **dropping or flagging** a film over showing wrong words. A
smaller, trustworthy corpus beats a bigger one with visible nonsense.

Deliverable: a pipeline that systematically detects every failure mode
below, picks a better file where one exists, and otherwise excludes or
flags the film - plus a repeatable audit that shows it worked.

## Read first

- `docs/sessions/2026-Q3/2026-09-25-content-consensus-selection.md` - what
  shipped (PR #41), the 100-film study, calibration, results.
- `docs/superpowers/plans/2026-09-24-content-consensus-selection.md` - the
  design + calibration numbers for the current selection.
- `docs/sessions/2026-Q3/2026-09-24-subtitle-file-selection.md` - PR #38
  (the size/band pre-filter, count-time doubled/sparse checks).
- `docs/PIPELINE-RESTORE.md` - VM runbook (updated 2026-09-25).
- `pipeline/src/moviewords_pipeline/consensus.py`, `counts.py`,
  `corpus_index.py`, `subtitle_parser.py`.
- Study data (outside the repo, on Andrew's laptop):
  `~/Projects/beveradb/moviewords-mislabel-study-2026-09-24/` - prototype
  scripts (`mw_*.py`), the 100-film study (`mw_s_*.jsonl`), and the
  pre-1968 "fuck" audit (see below).

## How selection works today (PR #41)

`index` pre-filters each OPUS folder by size (5-400 est. words/min at 24.5
bytes/word, no outsized doubles) and samples up to 12 candidates. `count`
fingerprints each one (top-300 content words, English-stopword share,
film-making-word rate, bytes/word), gates out commentary / not-English /
sparse / tiny, groups near-identical files (cos >= 0.98) into one "text",
and picks the median-length file of the group with the most agreeing texts
(cos >= 0.85), then most files, then rank. If every file fails the gates,
the gates are **relaxed** (e.g. musicals, whose lyrics are stripped).
`work/selection.parquet` records every film's reason (consensus / single /
rank / doubled), cluster size, and rejections.

As of 2026-09-25: 64,633 films; 45,704 by consensus, **17,435 single-file**,
1,488 by rank (nothing agreed), 263 relaxed.

## The evidence: pre-1968 "fuck" audit

This is the best canary we have. Files in the study folder:

- `pre1968-fuck-before.csv` (146 films, live data before PR #41),
  `pre1968-fuck-after.csv` (131 after), `pre1968-fuck-comparison.csv`.
- `pre1968-en-fuck-lines.txt` - every English-original hit with context.
- `pre1968-en-fuck-verdicts.csv` - a verdict for each of the 39 English-
  original films.

The 39 English-original films break down as:

| Verdict | n | Examples |
|---|---|---|
| genuine / likely | 7 | Portrait of Jason, Warrendale, Titicut Follies, Dont Look Back, Chelsea Girls, David Holzman's Diary, My Hustler |
| uncertain | 3 | Primary, Herostratus, The Touch of Her Flesh |
| **back-translated** English | 18 | Young Cassidy, Little Shop of Horrors, Santa Fe Passage, Happy Go Lovely, Banning ("Fuck the cow yellow") |
| **auto-captions (ASR)** | 7 | Arizona, The Thirteenth Guest, Murder in the Private Car, Smoky |
| transcriber guess | 2 | The Nasty Rabbit ("Fuck (indistinct)"), What's Up, Tiger Lily? |
| **wrong film** | 2 | Sunrise 1927, Lady Luck 1946 |

The ~92 non-English films are mostly legitimate translator choices, but they
still merit a look.

## Failure modes - catalogue

For each: what it looks like, how to detect it, the current state, and what
to do. Numbers are from the 2026-09-24/25 work unless noted.

### 1. Wrong film filed under the IMDb id (mislabel)
- **Looks like:** another film's character names (Othello → O 2001's odin/hugo;
  Werewolf → Bee Movie). Often an upload error, or a same-title / remake mix-up
  (The Grudge → Ju-On, Confirmation 2016 under The Confirmation).
- **Handled when:** the folder has several files and most are genuine (consensus).
- **Still leaks:**
  - **Single-file folders** - nothing to vote with.
  - **Majority-wrong folders** - Vinaya Vidheya Rama (blocklisted).
  - **Duplicate copies winning the "more files" tie-break** - Lady Luck: 2
    identical uploads of a modern film beat 1 genuine file when nothing agreed.
- **Detect:**
  - **TMDB cast-name check (strongest, works for single files too).**
    Fetch TMDB credits (character names). A subtitle that names *none* of
    the film's characters while naming another film's is almost certainly
    wrong. Proven in the 2026-09-24 pair scan
    (`mw_pairs_tmdb.py`: 66 pairs adjudicated, clear cases precise).
    Caveats: documentaries (cast = "Himself"), silents, films with few
    named characters - treat "no names either way" as unknown, not wrong.
  - Cross-film duplicate scan (`scripts/scan_mislabels.py`). Its rare-word
    window (2-20 films) is far too narrow - use ~2-300 - and its stage-3
    consensus threshold (0.8) is saturated by the stopword floor (use
    content-word cosine). The prototype in `mw_pairs_tmdb.py` is better.
  - Anachronism check: modern vocabulary in old films (internet, cellphone,
    email, computer, okay-heavy slang, brand names) - Lady Luck 1946 had
    "Jesse James Desperado, bitch".
- **Do:** use cast-name agreement as a consensus input (a tie-breaker, and
  a veto for single files); drop films whose only file fails it.

### 2. The pre-filter excludes the genuine files (silent films)
- **Sunrise 1927:** 7 genuine intertitle-only files (~350 words) fall below
  the index's 5 words/min floor, so the only in-band file (a Spanish-
  language thriller) wins as "single".
- **Do:** don't hard-exclude low-rate files when they cluster; or lower the
  floor (~2/min); or run consensus over all parseable files and use the band
  only as a tie-breaker. Also consider: TMDB genre/era says silent → expect
  a low word rate.

### 3. Back-translated "English" subtitles (biggest new class)
- **Looks like:** right film (character names match) but the English was
  machine-translated from another language's subtitles: broken grammar
  ("Mules not drink if in water there are corpses"), leftover source-
  language debris (Portuguese "Já vÃm", Greek ";" question marks, Vietnamese
  "cùu"), MT artifacts ("not", "do", "will" surfacing as *distinctive*
  words), and modern swearing in 1930s-60s films.
- **Handled when:** a better English file exists and outvotes it - usually
  not the case for old or obscure films.
- **Detect (to prototype + calibrate):**
  - A **language-model fluency score** (perplexity under a small English
    LM, or n-gram plausibility vs a clean reference corpus).
  - Stopword-bigram profile ("not do", "will you going") vs genuine files.
  - Non-ASCII / other-language token rate (debris).
  - Distinctive-word artifacts: common function words appearing in the
    log-odds `distinctive` list is a strong smell.
  - OPUS metadata: many lack `<date>`/`<source>` (uploaded via newer paths).
    Weak on its own.
- **Do:** prefer a fluent file when one exists; otherwise flag the film
  (see "Policy" below).

### 4. Auto-generated captions (ASR)
- **Looks like:** unpunctuated, run-on "sentences" of 50-200 words, all
  lowercase or randomly cased, misheard words ("Oh fire me bite me here fuck
  me again"). Common for 1930s-40s B-movies (YouTube auto-captions).
- **Detect:** punctuation per word, mean sentence length, capitalisation
  ratio, the share of subtitle blocks without terminal punctuation. Very
  separable - calibrate on the 7 known cases vs a random sample.
- **Do:** a gate (skip when alternatives exist), otherwise flag or exclude.

### 5. Commentary tracks and featurettes
- Gated since PR #41 (film-making-word rate >= 8 per 1k AND < 18 bytes/word):
  896 rejected. **Residual risk:** if a film's *only* file is commentary,
  the gates relax and it is published anyway. Same for not-English.
- **Do:** relaxation should only apply to benign gates (sparse = musicals).
  A film whose only files are commentary or other-language should be
  **dropped**, not published.

### 6. Wrong language
- Gated (English-stopword share < 0.25), e.g. Philadelphia (Vietnamese).
  OPUS's `<confidence>` is unreliable (1.0 on a German file). Same
  relaxation leak as #5. Mixed-language genuine films (Inglourious Basterds
  at 0.27) sit near the threshold - calibrate carefully.

### 7. Transcriber guesses / SDH artefacts
- "Fuck (indistinct)." - the parser drops bracketed cues but not a guessed
  word beside one. "Egad! Fuck!" in What's Up, Tiger Lily? is likely
  misheard. Hard to detect generically; the anachronism canary (#11) is the
  practical net.

### 8. OCR errors
- `lago` for Iago (Othello), `l'm`/`lt's`, `i'ii`/`aii` (Chelsea Girls:
  `i'ii iike you'ii aii`), letter-spaced text ("N E WRITE S TO TH E C O LO N E L").
  These pollute distinctive words and counts.
- **Detect:** OOV rate against an English wordlist; known OCR confusion
  pairs (l↔I, ii↔ll, rn↔m).
- **Do:** normalise the common confusions in the tokenizer (carefully -
  `lt` is not always `It`), or prefer lower-OCR-error files in consensus.

### 9. Formatting junk
- Fixed in PR #41: SSA `{\...}`, mangled `font color=...`, `nbsp`.
- Remaining: release-group credit animations (`© P@rM!`, `nder M@nk...`),
  `yyy`/`yyyi` tokens from mis-decoded bytes (Match Point, Just Like Heaven,
  Envy...), half-byte-swapped UTF-16 (gated as sparse).
- **Do:** credit-line patterns in `CREDIT_RE`; drop tokens made of repeated
  `y`; consider a per-file junk-token rate as a gate.

### 10. Truncated / doubled / partial / forced-only files
- Handled by PR #38 (the band + upper-quartile cap) and PR #41 (median
  length within the cluster, doubled-file guard). Keep regression tests.

### 11. Cross-cutting canaries (build these as a repeatable audit)
- Profanity before 1968, per word (fuck, shit, motherfucker...), English-
  original first.
- Anachronisms: words that can't appear before a year (internet, email,
  cellphone, smartphone, google, texting, laptop, wifi...).
- Films whose `distinctive` words include function words (MT smell) or
  names from another film (cast check).
- Word rate outliers vs runtime/genre (silent < 10 wpm, talky > 200).
- Before/after diffs of every one of these on each rebuild.

## Policy questions for Andrew (ask early)

1. **Exclude or flag?** For a film whose only subtitle is back-translated or
   ASR: drop it from the corpus entirely, or keep it with a visible "subtitle
   quality: low" note and exclude it from aggregates, rankings and Trends?
   (Recommendation: exclude from all aggregates and rankings; keep the movie
   page with a clear note, or drop it if it's egregious.)
2. How much corpus shrinkage is acceptable? Measure it before deciding:
   count films per failure mode across the whole corpus first.
3. Should "translated" (non-English-original) films be held to the same
   fluency bar? Their subtitles are translations by nature; the issue is
   *machine* back-translation, not human translation.

## Suggested approach

1. **Measure first (no publish).** Add per-file quality features to the
   fingerprint (punctuation rate, mean sentence length, OOV/OCR rate,
   non-ASCII rate, a fluency score, TMDB cast-name hits). Compute them over
   the whole corpus on the VM - one sharded pass, ~25 min with the local
   zip. Calibrate on the labelled 39 (`pre1968-en-fuck-verdicts.csv`) plus
   a fresh random sample of ~100 films read by eye.
2. **Decide the policy** with Andrew using the counts.
3. **Implement:** gates/vetoes in `consensus.choose`, a per-film quality
   tier in `selection.parquet`, and the chosen policy in `derive` (exclude
   or flag). Fix the relaxation leak (#5/#6) and the silent-film floor (#2).
   Bump `FINGERPRINT_VERSION` if features change (refetch - that's the
   one-hour VM pass) or only `SELECTION_VERSION` if the features are already
   cached.
4. **Audit:** rerun every canary in #11 and diff it; read samples by eye;
   check the known cases (Sunrise, Lady Luck, Young Cassidy, Arizona,
   Othello, Philadelphia, Baahubali 2, Heat).
5. **Publish** (Andrew approves first), PR, verify prod, delete the VM.

## Running it on the VM (fast, and independent of the laptop)

Everything long-running should run on the VM, detached, so Andrew's laptop
can sleep or restart. The scripts are in `pipeline/scripts/vm/`
(`bootstrap.sh`, `count.sh`, `bake.sh`, `upload.sh`), each writing
`/opt/<step>.log` and touching `/opt/<STEP>_DONE`.

**Setup (from the laptop):**
```bash
# 1. VM next to the OPUS server (CSC, Finland); 8 vCPU for 8 count shards
gcloud compute instances create moviewords-pipeline-tmp --project=nomadkaraoke \
  --zone=europe-north1-a --machine-type=n2-highmem-8 --boot-disk-size=200GB \
  --image-family=debian-12 --image-project=debian-cloud
#    (consider --boot-disk-type=pd-ssd: pd-standard is slow for 800k small files)
# 2. R2/CF creds -> /tmp/mw_r2.env (chmod 600): see the moviewords-deploy-ops
#    memory for deriving R2 keys from MOVIEWORDS_CF_TOKEN. Also the ratings
#    cache: tar the main clone's data/work/tmdb_release (4.8MB zst).
gcloud compute scp --zone=europe-north1-a /tmp/mw_r2.env /tmp/mw_tmdb_release.tar.zst \
  pipeline/scripts/vm/*.sh moviewords-pipeline-tmp:/tmp/
# 3. Kick off bootstrap -> count chained, fully detached:
gcloud compute ssh moviewords-pipeline-tmp --zone=europe-north1-a --command \
  'sudo setsid bash -c "bash /tmp/bootstrap.sh <branch> && bash /tmp/count.sh" </dev/null >/dev/null 2>&1 &'
```

**Rules learned the hard way:**
- **Detach properly:** `sudo setsid bash -c "..." </dev/null >/dev/null 2>&1 &`.
  A plain `nohup ... &` inside `gcloud compute ssh` can keep the SSH session
  open (it hung for 5 min and was killed).
- **Never `exec > >(tee log)` + bare `wait`** - it deadlocks (~1h lost).
  Wait on explicit PIDs (count.sh does).
- **Marker files + logs, then poll** with short, independent `gcloud ssh`
  checks. A laptop-side watcher loop must treat a failed check (DNS blip,
  laptop sleep) as "still running", not "done" - one watcher exited early on
  a DNS error.
- **Run as root consistently** (`sudo bash -c`): the repo is root-owned, and
  `git` as the login user fails with "dubious ownership".
- **Delete macOS `._*` files** after extracting a tar made on a Mac (113k of
  them broke derive). bootstrap.sh does this.
- **Use a current rclone** (>= 1.65; Debian ships 1.60 → a 501 per unchanged
  R2 object). `upload_r2.sh` sets `RCLONE_RETRIES=1` - default retries
  re-check ~770k files per attempt (~2h wasted).
- **Download the OPUS zip onto the VM** (34GB in ~10 min from europe-north1)
  rather than HTTP ranges: no load on the OPUS server, no throttling.
- **pkill patterns:** use a char class (`"cli[ ]count"`) so pkill doesn't
  match its own SSH command line.
- **Archive the grown `data/work` to R2 before deleting the VM**
  (PIPELINE-RESTORE.md, "Refreshing the archive"). The latest is
  `moviewords-work-cache-2026-09-25.tar.zst` (940MB, with per-file
  fingerprints: a `SELECTION_VERSION`-only change re-chooses in ~2 min).

**Measured timings (n2-highmem-8, europe-north1, 2026-09-24/25):**

| Step | Time |
|---|---|
| bootstrap (apt, clone, 800MB cache from R2, 34GB zip) | ~15 min |
| index (local zip) | ~20 s |
| count, 8 shards, full refetch of 242k files | ~25 min |
| re-choose only (SELECTION_VERSION bump) | ~2 min |
| compaction (final unsharded count) | ~3 min |
| derive en / all | 11 / 16 min |
| rebuild_web_data en / all | 10 / 17 min |
| bake_all_languages + ratings | ~20 min |
| upload: ~770k files, most unchanged | pass 1 ~80 min, passes 2-3 ~16 min |
| cost | ~$0.50/h; the whole run ~$3 |

**Speed ideas not yet tried:** pd-ssd or a local-SSD scratch disk for
`webdata/out`; bake languages in parallel processes (they're independent);
derive en and all in parallel (64GB RAM is enough).

## Loose ends from 2026-09-25

- 2 wrong films live now: **Sunrise (tt0018455)** and **Lady Luck
  (tt0038680)**. Quick stopgap: blocklist their current files
  (`mislabeled_subs.txt`). For Sunrise, fixing the floor lets the genuine
  intertitle files win instead of dropping the film.
- Cache records from PR #41's run lack `selection.runtime_minutes`, so the
  next `count` re-chooses every film once from fingerprints (~2 min, no
  reads unless a pick changes).
- `scan_mislabels.py` improvements (window, content cosine) are folded into
  #1 above.
