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
# Subtitle-file pre-filter (corpus_index.rank_candidates). A candidate's word
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
# Silent films' genuine files are intertitles only (Sunrise 1927: ~350 words
# in 94 min), below MIN_WORDS_PER_MIN - which left an in-band file of another
# film as the only candidate. Before talkies took over, let low-rate files
# in and let content consensus decide.
SILENT_ERA_END_YEAR = 1930
SILENT_MIN_WORDS_PER_MIN = 1
FALLBACK_WORD_RANGE = (2_000, 40_000)  # when runtime unknown
# Within the band, prefer files with a size peer: another candidate at most
# this ratio away (see corpus_index.rank_candidates).
MAX_PEER_SIZE_RATIO = 1.25
# ...and with at least MIN_CANDIDATES_FOR_CAP in band, skip files bigger than
# this multiple of the in-band upper-quartile size (paired doubled files).
MAX_SIZE_VS_UPPER_QUARTILE = 1.5
MIN_CANDIDATES_FOR_CAP = 4
# A candidate parsing to more than this many raw bytes per counted word
# (normal: ~25) is suspect - mis-encoded garbage, or a file that is mostly
# stripped lyrics/SDH cues - and is gated out of the consensus (unless every
# candidate is, as with musicals).
MAX_BYTES_PER_WORD = 60
# A pick counting faster than this (words/min of runtime) is checked for
# being a doubled file: a cluster member with 40-60% of its words replaces it.
# Real fast talkers (Get Shorty, His Girl Friday) have no such half-size twin.
MAX_COUNTED_WPM = 200

LANG = "en"

# Content-consensus selection (consensus.py). An OPUS folder holds one file
# per upload: mostly the same text re-synced/edited (content-word cosine
# 0.97-1.0), some independent translations (0.6-0.8), and a few harmful
# outliers (commentary tracks, wrong films/languages). The index samples up
# to CONSENSUS_MAX_CANDIDATES per film; the count stage fingerprints them all
# and takes the most typical file of the largest agreeing cluster.
CONSENSUS_MAX_CANDIDATES = 12
CONSENSUS_AGREE_COSINE = 0.85
# Files at least this similar are the same text (re-uploads, re-syncs) and
# get one consensus vote between them.
CONSENSUS_DUPLICATE_COSINE = 0.98
FINGERPRINT_WORDS = 300
# Gates, calibrated 2026-09-24 (docs/superpowers/plans/2026-09-24-content-
# consensus-selection.md): normal files have 43%+ English stopwords (p1),
# wrong-language ones ~7%; commentary tracks run 8-24 film-making words per
# 1k tokens (normal p99 9.3) AND are dense (13-16 bytes/word, normal ~24).
MIN_STOPWORD_SHARE = 0.25
COMMENTARY_MIN_RATE = 8.0
COMMENTARY_MAX_BYTES_PER_WORD = 18.0
MIN_CANDIDATE_TOKENS = 200
# Bump FINGERPRINT_VERSION whenever parsing or tokenizing changes: every
# cached fingerprint and count is refetched. Bump SELECTION_VERSION when only
# consensus.choose changes: choices are re-made from cached fingerprints
# (only a newly chosen file whose full counts weren't kept is read).
# Quality flags (consensus.quality_flags; calibration in docs/superpowers/
# plans/2026-09-25-subtitle-quality.md). A file of an English-original film
# at or above MT_SCORE_MAX on the machine-translation style model is
# flagged; so is one naming none of the film's cast while another
# candidate names CAST_MIN_HITS+ of them.
MT_SCORE_MAX = 0.8
CAST_MIN_HITS = 2
FINGERPRINT_VERSION = 2   # 2: quality features (fp["q"]), OCR repair, credit junk
# 2: distinct-text voting (Baahubali 2); 3: quality tiers, hard gates;
# 4: no hard gates, style model for English-original only, relative cast rule
SELECTION_VERSION = 4
