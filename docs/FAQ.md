# FAQ - methodology, limitations, and licensing

Honest answers to the questions a skeptical reader should ask. Deeper
technical detail lives in [ARCHITECTURE.md](ARCHITECTURE.md); the dataset
download guide is [DATA.md](DATA.md).

## Methodology

### Subtitles aren't scripts. Isn't this measuring subtitlers, not screenwriters?

Partly, yes - and we'd rather say so than pretend otherwise. Subtitles are
community-made transcriptions: OCR'd, occasionally condensed, occasionally
mistimed. We treat them as a good proxy for spoken dialogue, not as
ground-truth screenplays. Mitigations:

- The parser strips SDH cues in ()/[], credit and URL lines, ♪ lyric lines,
  timestamps, and formatting tags before counting.
- Every tokenizer rule (apostrophe-run collapse, quote-pair stripping that
  spares contractions, diacritic folding, digit-adjacent rejection, and more)
  was motivated by a real artifact found in the corpus and is pinned by a
  test.
- In OCR-damaged files, I/l and ll/ii confusions (`l'm`, `lt's`, `i'ii`) are
  repaired before counting.
- Aggregate views (trends, decade/genre signatures) average over thousands of
  films, so individual transcription quirks wash out; single-film pages are
  where a bad subtitle file would show - see the next two answers and
  [DATA-QUALITY.md](DATA-QUALITY.md).

### How do you pick which subtitle file to use for a film?

One file per film, chosen by content consensus. A film's folder holds one file
per OpenSubtitles upload; we keep files with a plausible word rate for the
runtime, read up to 12 of them, and take the most typical file of the largest
group that agree with each other. Commentary tracks, files in another
language, auto-generated captions, machine-translated "English", and files
that name none of the film's characters while another upload does are passed
over. The full story, with examples: [DATA-QUALITY.md](DATA-QUALITY.md).

### Why do some films say "Subtitle quality: low"?

Every subtitle we have for them is auto-generated captions, looks
machine-translated from another language, or contains words that couldn't
have been said in the film (like "fuck" in a 1950s Hollywood film). About 0.8%
of films. They keep their page so you can still look them up, but their words
are left out of every total, trend, chart, and ranking.

### Why do a few films before 1969 still use "fuck"?

Because they really did. Hollywood's Production Code banned profanity until
the MPAA ratings replaced it in late 1968, but 1960s documentaries and
underground films recorded real, unscripted speech - Warrendale, Portrait of
Jason, Chelsea Girls, Titicut Follies, Dont Look Back. Before the fixes in
[DATA-QUALITY.md](DATA-QUALITY.md), dozens of 1930s-60s films showed it too;
those came from machine-translated, auto-captioned, or wrong-film subtitles.

### What about non-English films?

They're in - as a second, clearly labeled corpus. The default view covers
films originally written in English, because a translated subtitle measures
the translator as much as the screenwriter. The header toggle switches the
whole site to "All films", which adds every non-English-original film in the
cut (badged with its original language). Same methodology, two honest
datasets - pick the one that matches your question.

### What's the "signature words" math?

Log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi & Quinn,
"Fightin' Words", 2008), using the whole corpus as the prior with alpha0=100.
A movie, a decade, and a genre are all just bags of words compared against
the corpus. Decade and genre signatures additionally require a word to appear
in at least 3 distinct films, so one film's OCR junk or character names can't
dominate an entity's list.

### Do you lemmatize or stem?

No - "run" and "running" are separate words, deliberately. Inflection choices
are part of how a film sounds. Contractions survive tokenization; hyphenated
words split.

### What decides "interesting words" vs "all words"?

Transparency over cleverness: wordfreq Zipf frequency >= 5.0 is tagged
"everyday" and hidden by default; WordNet supplies part-of-speech classes;
words WordNet doesn't know get class "x", which in practice is mostly
character names. The stopword and profanity lists the site uses are published
verbatim at `json/wordlists.json`.

### Old decades look noisy or weird. Why?

The corpus thins fast before ~1960, and surviving old films skew toward
canonized titles and particular genres - so decade comparisons partly reflect
corpus composition, not just how people talked. Years with too few films are
hidden from trend charts outright (the chart footnote lists them).
`word_year.parquet` ships a `movie_count` column per (word, year) so you can
normalize per-film in your own analysis.

### How accurate is "words per minute"?

Approximate. It divides subtitle word counts by IMDb runtimes, which don't
always match the cut the subtitle was made for. The subtitle-selection band
already rejects gross mismatches, but treat WPM as an estimate, not a
measurement.

### Is this corpus representative of cinema?

No - it's representative of *popular, subtitled* cinema. OpenSubtitles covers
what people watch and subtitle, and we additionally require >= 300 IMDb
votes. That's a deliberate floor (it also keeps metadata quality up), and it
means the dataset is a corpus of widely-seen film, not a census of everything
ever made.

## Licensing and ethics

### Isn't this built on copyrighted subtitles?

The published dataset contains only per-film word frequencies - unordered
(word, count) pairs. Word order is destroyed at count time and never
persisted; no line of dialogue can be reconstructed from anything we publish.
Word frequencies are facts *about* a work, not the work's expression. The
34GB source corpus never leaves the build machine.

### What do OPUS and OpenSubtitles actually allow?

OPUS distributes OpenSubtitles-derived corpora for research use and asks for
citation of Lison & Tiedemann (2016) plus a link to opensubtitles.org - both
appear in the site footer, the README, and the data guide. We redistribute
none of the corpus itself, only derived counts.

### Why is the dataset CC BY-NC-SA instead of something more permissive?

`movies.parquet` carries fields derived from the IMDb non-commercial datasets
(ratings, votes, runtimes, genres), which are licensed for non-commercial use
only. The strictest upstream term wins, so the whole published bundle is
non-commercial. The word counts alone could arguably be freer - the bundle
can't. See [LICENSE-DATA.md](../LICENSE-DATA.md).

### You're rehosting ~50,000 movie posters.

Posters are studio promotional artwork, sourced via the TMDB API and
self-hosted so that a traffic spike hits our bucket rather than TMDB's CDN.
They are used solely at small size to identify the films being discussed -
the classic use of identifying promotional imagery. This product uses the
TMDB API but is not endorsed or certified by TMDB. Any rights holder who
wants an image removed: email andrew@beveridge.uk and it comes down promptly.

### Some of the data is profanity-heavy. Is that editorial?

No - it's what the corpus says. Swear-rate stats and profanity trend lines
come from a published wordlist applied uniformly to every film. We show the
data; we don't curate words out of it.

### Something looks wrong / I found a bug in the data.

Email [andrew@beveridge.uk](mailto:andrew@beveridge.uk) or open an issue on
[GitHub](https://github.com/beveradb/moviewords). Several of the fixes in
[DATA-QUALITY.md](DATA-QUALITY.md) started as reports like that. Corrections to the
pipeline are welcome - every derivation step is open source and reproducible
from the runbook in `pipeline/README.md`.

## Privacy

### Do you track me? What analytics do you use?

No cookies, no personal data, no cross-site tracking - so there's no consent
banner to click. We use Cloudflare Web Analytics and GoatCounter, both
cookieless: they record aggregate hits (which page, roughly where in the world,
what referred you) with no identifiers that follow you around. That's enough to
see how the site is doing after launch, and nothing more.
