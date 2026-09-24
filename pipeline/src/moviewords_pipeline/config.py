from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WORK_DIR = DATA_DIR / "work"
OUT_DIR = DATA_DIR / "out"

OPUS_URL = "https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2024/raw/en.zip"
IMDB_BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"

MIN_VOTES = 300
# Subtitle-file selection (corpus_index.select_best). A candidate's word
# count is estimated from its raw OPUS XML size: measured over the 51.7k
# chosen files (2026-09-24) that's 24.5 bytes/word at the median (p5-p95
# 18-33). The old estimate was size/8 - 3x too high - so the 250/min cap
# really meant ~80 words/min and rejected every full-length file of talky
# films (GoodFellas, The Social Network...), leaving featurettes or nothing.
BYTES_PER_WORD = 24.5
# Plausible spoken-word rate band, in estimated words per minute of runtime.
# Deliberately wide: silent films sit at 5-10, the rest at 25-150.
MIN_WORDS_PER_MIN = 5
MAX_WORDS_PER_MIN = 400
FALLBACK_WORD_RANGE = (2_000, 40_000)  # when runtime unknown
# Within the band, prefer files with a size peer: another candidate at most
# this ratio away (see corpus_index.rank_candidates).
MAX_PEER_SIZE_RATIO = 1.25
# A top pick that parses to more than this many raw bytes per counted word
# (normal: ~25) is suspect - mis-encoded garbage, or a file that is mostly
# stripped lyrics/SDH cues. The count stage then also counts up to
# MAX_ALTERNATES next-ranked files and keeps whichever yields the most words
# (so genuinely sparse films like musicals keep their pick).
MAX_BYTES_PER_WORD = 60
MAX_ALTERNATES = 3

LANG = "en"
