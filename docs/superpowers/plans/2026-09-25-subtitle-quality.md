# Subtitle quality tiers - design and calibration (2026-09-25)

Follow-up to `docs/handoffs/2026-09-25-subtitle-data-quality.md`. Bar:
the site must never show inaccurate data. Prefer leaving a film out of the
numbers over showing wrong words.

## Policy (Andrew, 2026-09-25)

- A film whose **only** usable subtitle is low quality (machine-translated,
  auto-captions, or naming none of its cast) is **left out of every
  aggregate** - totals, trends, boards, superlatives, signatures, language
  and rating slices - but **keeps its film page** with a "Subtitle quality:
  low" note saying why.
- A film whose only files are **not its dialogue at all** (a commentary
  track, another language) is **dropped**.
- Machine translation is judged the same way for every film, whatever its
  original language. Human translations are fine; the target is machine
  output.
- No stopgap publish for Sunrise / Lady Luck; the structural fix covers
  them.

## Pipeline

| Stage | Change |
|---|---|
| `index` | Pre-1930 films admit files down to 1 word/min (silent films' intertitle-only files; Sunrise's genuine files were below the 5/min floor) |
| `count` | `FINGERPRINT_VERSION` 2: every candidate's fingerprint gains `q` (quality features, `quality.features`); `count_words` repairs OCR I/l and ll/ii confusions in OCR-damaged files; credit-animation lines are dropped |
| `count` | `SELECTION_VERSION` 3: `consensus.choose` flags files (`quality_flags`) and prefers unflagged ones; tiers ok / low / drop in `selection.parquet` |
| `credits` (new) | TMDB cast lists (`work/tmdb_credits/`), one request per film |
| `derive` | `movies.parquet` + `words_by_movie` = tier ok only (every aggregate reads them); tier low -> `movies_flagged.parquet` + `words_by_movie_flagged` -> film pages with a `quality` field |
| web | `movies-index.json` entries for tier-low films carry `"q": "low"`; the app's client-side counts skip them (`inCorpus`), search keeps them |
| audit | `scripts/audit_quality.py` - the canaries, with `--baseline` diffs |

### Gates and flags

- **Hard gates** (never relaxed; film dropped if every file fails):
  `commentary`, `not-english`.
- **Relaxed gates** (kept if every file fails): `tiny` (near-wordless films:
  Silent Movie says one word, The Red Turtle none) and `sparse` (musicals).
  The first draft made `tiny` hard; the baseline audit showed the lowest
  word-rate films are genuinely near-wordless, so it was reverted.
- **Quality flags** (prefer unflagged files; tier low if all flagged):
  - `asr` - `toks_per_line >= 12 and cap_start < 0.75 and end_punct < 0.6`
  - `machine-translated` - OPUS `<machine_translated>1` or style-model
    score >= 0.7
  - `wrong-cast` - names none of the cast (broad tokens) while another
    candidate names 2+; or, for English-original fiction with 5+
    distinctive cast names, names none at all

## Calibration

Labelled data: the 39 English-original pre-1968 films with "fuck" (read
line by line, `pre1968-en-fuck-verdicts.csv`) plus files read by eye while
calibrating. Samples: 1,500 + 200 held-out genuine files (English-original,
consensus cluster >= 6, pre-2018 uploads), 450 newer-schema consensus files,
300 random English-original, 200 random pre-1960, 200 random non-English.
Study scripts and data: `~/Projects/beveradb/moviewords-quality-study-2026-09-25/`.

### Auto-captions: trivially separable

| | tokens/line p50 | cap_start p50 | end_punct p50 |
|---|---|---|---|
| ASR (7) | 23.1 (min 18.2) | 0.46 (max 0.58) | 0.23 (max 0.43) |
| random (300) | 5.4 (p99 9.1) | 0.99 (p1 0.89) | 0.99 (p1 0.83) |

### Machine translation: what didn't work

- Punctuation, sentence shape, contraction ratio alone: overlapping.
- **Trigram LM fluency** (stupid backoff, trained on 1,500 genuine files):
  back-translated median -1.94 log10/token vs genuine -1.91. Modern MT is
  locally fluent.
- **Vocabulary era** (naive Bayes over decade unigram models): back-
  translations sound era-typical (median 3.5 years off) - MT maps most
  words back. It *does* expose wrong films: Lady Luck 1946 reads as 1990s,
  Sunrise 1927 as 2000s. 1960s documentaries (candid speech) read modern.
- OPUS metadata: the `machine_translated` flag is set on 1 file in 2,150;
  newer uploads (file id > ~1,955.6M) have minimal metadata, and while 22
  of 25 bad files were newer uploads, so are 58% of random picks.

### Machine translation: the style model

Logistic regression on per-1k-token rates of the 400 commonest words in
genuine subtitles (`style_words_en.txt`), 7 contraction-suffix rates and
the n't/(n't+not) ratio. `bt_model_en.json`, C=0.05, balanced classes.
MT English overuses "not", "do", "will", "but", "these", uncontracted forms;
underuses "there's", "'s".

- 31 positives (18 labelled + 13 found by reading top-scoring unlabelled
  files, incl. two whole consensus clusters that are MT), 2,160 negatives.
- 6-fold CV AUC **0.974**. At 0.7: recall 26/31 (84%), false positives
  3/2,160 (0.14%). Human translations of non-English films score low (max
  0.22 over 150 consensus-backed ones).
- Unlabelled pre-1960 sample: 14/200 score >= 0.5; of those read, most are
  MT ("Living in secret is like lying a lie", "Mrs Chalon, no welcomed
  you?"); false positives are formal/accented dialogue (The Happy Time).
- Retrain: the style counts are cached per file (`fp["q"]["style"]`), so a
  new model is a `SELECTION_VERSION` bump - no refetch.

### Cast names

`quality.cast_tokens`: each character's name (the actor's for self-roles).
Strict tokens are distinctive (zipf < 2.5, or < 4.0 and not a WordNet
word); broad tokens are every non-stopword. On 6,630 genuine rich-cast
films the absolute rule's false-positive rate was 0.11% - all
documentaries, experimental or non-English films - hence "absolute" only
for English-original fiction. The relative rule flagged 263 files in 18.5k
multi-file folders; read samples were nearly all wrong films (The Fog of
War: a file about Amazon plants; Star Trek: Nemesis: "browser, interface,
viewports").

### OCR repair

In files with 3+ unambiguous markers (`l'm`, `l'll`, `lt's`, `i'ii`,
`you'ii`...), each token is swapped for its best I/l or ll/ii variant when
that is a common word (zipf >= 3) at least 2 zipf above the token (wordfreq
splits `i'ii` into two words - such tokens count as unknown). 4.9% of
files trigger; the corpus had l'm x21k, lt's x20k, lf x18k, lt x17k, l'll
x17k, ls x15k, i'ii x13k. Names survive (Lan/Ian, Lra/Ira); Roman numerals
(lll, iii) are left alone.

## Open

- A cross-film scan (whose cast does a file name?) would turn "names none
  of its cast" into "names another film's cast" - stronger evidence for
  single-file folders.
- The vocabulary-era score could join the audit as a wrong-film canary.
