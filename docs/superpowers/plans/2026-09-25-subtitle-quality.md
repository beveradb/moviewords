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
- Machine translation is judged the same way for every film, whatever its
  original language. Human translations are fine; the target is machine
  output. **In practice** the style model can only tell machine output
  from human translation in English-original films (see below), so for
  translated films only OPUS's own `machine_translated` flag counts.
- No stopgap publish for Sunrise / Lady Luck; the structural fix covers
  them.
- A first draft also *dropped* films whose only files were commentary or
  another language (the handoff's "relaxation leak"). Reading the 205 it
  dropped showed they were nearly all genuine (below), so nothing is
  dropped: gates relax as before.

## Pipeline

| Stage | Change |
|---|---|
| `index` | Pre-1930 films admit files down to 1 word/min (silent films' intertitle-only files; Sunrise's genuine files were below the 5/min floor) |
| `count` | `FINGERPRINT_VERSION` 2: every candidate's fingerprint gains `q` (quality features, `quality.features`); `count_words` repairs OCR I/l and ll/ii confusions in OCR-damaged files; credit-animation lines are dropped |
| `count` | `SELECTION_VERSION` 6: `consensus.choose` flags files (`quality_flags`) and prefers unflagged ones; tier ok / low (+ flags, flagged) in `selection.parquet` |
| `credits` (new) | TMDB cast lists (`work/tmdb_credits/`), one request per film |
| `derive` | `movies.parquet` + `words_by_movie` = tier ok only (every aggregate reads them); tier low -> `movies_flagged.parquet` + `words_by_movie_flagged` -> film pages with a `quality` field |
| web | `movies-index.json` entries for tier-low films carry `"q": "low"`; the app's client-side counts skip them (`inCorpus`), search keeps them |
| audit | `scripts/audit_quality.py` - the canaries, with `--baseline` diffs |

### Gates and flags

- **Gates** (unchanged from PR #41): `commentary`, `not-english`, `sparse`,
  `tiny`. When every file fails one, the gates relax and the best file is
  kept. The first full run tried hard gates; of the 205 films it dropped,
  199 were "commentary-only" and were documentaries about film-making whose
  real dialogue is film talk (Life Itself, QT8, Milius, Ringers: Lord of the
  Fans, Making Prometheus, Butterfly Kisses), and the 6 "other-language"
  ones were near-wordless or invented-language films (Shaun the Sheep:
  Farmageddon, When Dinosaurs Ruled the Earth, Baraka). The lowest word-rate
  films are genuinely near-wordless too (Silent Movie says one word).
- **Quality flags** (prefer unflagged files; tier low if all flagged):
  - `asr` - `toks_per_line >= 12 and cap_start < 0.75 and end_punct < 0.6`
  - `machine-translated` - OPUS `<machine_translated>1`, or (English-
    original films only) style-model score >= 0.8
  - `wrong-cast` - names none of the TMDB cast while another candidate
    names 2+ of them (steers selection; a film only lands in tier low if
    every file is flagged for something)
  - `anachronism` - strong profanity (fuck*, motherfuck*, cunt) in an
    English-original, non-documentary film from before 1965. Checked on
    every candidate's fingerprint (the published profanity list) and on the
    chosen file's full counts (other forms: "fucked", "fuckin").

### Results (full corpus, 2026-09-25)

64,648 films: **64,116 tier ok, 532 tier low** (0.8%) - 414 machine-
translated (411 English-original), 83 auto-captions, 33 anachronism (mostly
with another flag), 1 other. By era, English-original: 5.7% of pre-1930,
2.4% of 1930-67, 1.0% of 1968-99, 1.3% of 2000+; translated films < 0.2%.
In another **1,684 films** a flagged upload was passed over for a clean one
(1,047 machine-translated, 527 wrong-cast, 123 auto-captions); 896 live picks
change. Canaries vs the live data: pre-1968 English-original strong
profanity 56 -> 12 films (8 genuine 1960s documentaries/underground films +
3 at the rule's 1965-66 edge + Primary); anachronisms 127 -> 100 (mostly
"dvd"/"online" in release-credit lines); known cases all right (Sunrise's
intertitles now win; Lady Luck's wrong copies are blocklisted).

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

- Round 1: 31 positives (18 labelled + 13 found by reading top-scoring
  unlabelled files, incl. two whole consensus clusters that are MT), 2,160
  negatives; CV AUC 0.974.
- Round 2 (after the first full run, reading every flagged bucket): 47
  positives, 2,020 English-original negatives (the model now judges only
  English-original films). 6-fold CV AUC **0.977**; at **0.8**: recall
  37/47 (79%), false positives 3/2,020 (0.15%).
- **Translated films:** on a read sample of 13 flagged non-English films
  only ~5 were MT - human translations of Italian, Finnish, Indian films
  read as "translationese" (Ben and Charlie 0.999, The Violin Player
  0.994; a real MT, Detective Conan, 0.787). No threshold separates them,
  hence English-original only.
- English-original flagged sample: ~18/20 MT ("Consigamos one." - Spanish
  debris; Greek ";" question marks; "It Rodge."). The 0.44-0.70 grey zone
  holds ~1 MT in 4 (Zombex, Evilution) among genuine period/formal
  dialogue (The Great Ziegfeld, OHMSS) - left as the audit's review list.
- Unlabelled pre-1960 sample: 14/200 score >= 0.5; of those read, most are
  MT ("Living in secret is like lying a lie", "Mrs Chalon, no welcomed
  you?"); false positives are formal/accented dialogue (The Happy Time).
- Retrain: the style counts are cached per file (`fp["q"]["style"]`), so a
  new model is a `SELECTION_VERSION` bump - no refetch.

### Cast names

`quality.cast_tokens`: each character's name (the actor's for self-roles),
every non-stopword token. Only the **relative** rule is used: a file naming
none of them while another candidate names 2+. It flagged 263 files in
18.5k multi-file folders on the v1 cache; read samples were nearly all wrong
films (The Fog of War: a file about Amazon plants; Star Trek: Nemesis:
"browser, interface, viewports"; Love Me Tender: "assassins, palace").

Rejected:
- An **absolute** rule (a lone file naming none of 5+ distinctive cast
  names): 0.11% false positives on genuine consensus files, but on the
  single-file folders it actually fires on, a read sample was mostly
  genuine narrated or sparsely-named films (Cronenberg's Stereo, Astral,
  Andhrudu). The two real wrong films it found are blocklisted (The Secret
  of My Success 1965 = the 1987 film; The Legend of Nigger Charley 1972).
- Dropping common words (zipf >= 5: "happy", "little") from the tokens,
  which would catch Lady Luck's wrong copies: it doubled the flags, adding
  genuine files of films whose characters are unnamed (The Road: "Man",
  "Boy"). Lady Luck's two wrong uploads are blocklisted instead.

### OCR repair

In files with 3+ unambiguous markers (`l'm`, `l'll`, `lt's`, `i'ii`,
`you'ii`...), each token is swapped for its best I/l or ll/ii variant when
that is a common word (zipf >= 3) at least 2 zipf above the token (wordfreq
splits `i'ii` into two words - such tokens count as unknown). 4.9% of
files trigger; the corpus had l'm x21k, lt's x20k, lf x18k, lt x17k, l'll
x17k, ls x15k, i'ii x13k. Names survive (Lan/Ian, Lra/Ira); Roman numerals
(lll, iii) are left alone.

## Open

- Single-file wrong films: a cross-film scan (whose cast does a file
  name?) would turn "names none of its cast" into "names another film's
  cast" - the evidence the absolute rule lacked.
- Machine translation in translated films: needs a model trained on human
  vs machine translations of foreign films (labelled data from reading).
- The grey zone (0.4-0.8, ~230 English-original films) holds some MT.
- The vocabulary-era score could join the audit as a wrong-film canary.
