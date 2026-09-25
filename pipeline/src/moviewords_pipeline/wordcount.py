import re
import unicodedata
from collections import Counter
from functools import lru_cache

import wordfreq

# Hyphenated words are deliberately split into separate tokens (e.g. "well-known" ->
# ["well", "known"]) since hyphens aren't part of this character class; this is intentional
# corpus-tokenization behavior, not an oversight.
#
# Boundary-guarded on both sides against adjacent word/digit characters so that a token
# glued to a digit (e.g. "1950s" -> "s", "42nd" -> "nd") is rejected outright instead of
# yielding a junk trailing/leading fragment. `\w` includes digits and underscore, so this
# also still excludes any [a-z']+ run directly touching another word character (there
# shouldn't be one post-lowercasing/accent-stripping, but the guard is cheap insurance).
TOKEN_RE = re.compile(r"(?<![\w'])[a-z']+(?![\w'])")

# Matches an apostrophe-quoted span that is functioning as a quotation mark rather than as
# part of a word, e.g. "she said 'no way' to him". The (?<!\w)/(?!\w) boundary checks mean an
# apostrophe directly touching a word character never qualifies as an opening or closing
# quote, so contractions ("don't") and elisions ("goin'", "'tis") are left untouched. Spans
# can't nest since the inner group excludes apostrophes, so a single pass is sufficient.
QUOTE_PAIR_RE = re.compile(r"(?<!\w)'([^'\n]+)'(?!\w)")


def tokenize(text):
    text = text.lower()
    # Curly (typographic) apostrophes are common in subtitle/script sources; normalize them
    # to the ASCII apostrophe so contractions like "don't" tokenize consistently regardless
    # of which apostrophe character the source used.
    text = text.replace("’", "'").replace("‘", "'")
    # OCR-era subtitle files often double apostrophes (don''t); collapse runs
    # so they merge with normal contraction tokens instead of forming one-film
    # artifact tokens that dominate log-odds signatures.
    text = re.sub(r"''+", "'", text)
    # Strip quote-functioning apostrophe pairs down to their inner span before extracting
    # tokens, so quoted phrases don't distort word counts with leading/trailing apostrophes.
    text = QUOTE_PAIR_RE.sub(r"\1", text)
    # Normalize accented Latin letters to their unaccented ASCII form (café -> cafe, naïve ->
    # naive) for consistent word-frequency aggregation; this is standard practice for word
    # frequency corpora. Non-Latin scripts still drop out via the [a-z'] token regex below.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    tokens = []
    for tok in TOKEN_RE.findall(text):
        if tok.startswith("'") and tok.endswith("'") and len(tok) > 1:
            tok = tok.strip("'")
        letters = tok.strip("'")
        # Single-letter tokens other than "a"/"i" are corpus noise (chat-speak "u",
        # OCR fragments, stranded elisions like "'t") — drop them.
        if letters and (len(letters) > 1 or letters in ("a", "i")):
            tokens.append(tok)
    return tokens


# OCR-ripped subtitles (read from DVD bitmaps) confuse I/l and ll/ii:
# "l'm", "lt's", "lf", "i'ii", "aii", "iike". In an OCR-damaged file these
# are thousands of junk tokens standing in for the commonest words. A file
# counts as OCR-damaged when it has several tokens that are unambiguous
# confusions; only then is each rare token swapped for a confusion variant
# that is a far commoner word (so names like Lan/Ian, Lra/Ira survive).
OCR_MARKERS = frozenset(
    "l'm l'll l've l'd lt's i'ii you'ii we'ii they'ii he'ii she'ii it'ii "
    "that'ii".split())
MIN_OCR_MARKERS = 3
OCR_MIN_ZIPF = 3.0
OCR_MIN_ZIPF_GAIN = 2.0


def _zipf(word):
    # wordfreq scores "i'ii" as the words "i" + "ii": a token it splits is
    # not a word it knows
    if len(wordfreq.tokenize(word, "en")) != 1:
        return 0.0
    return wordfreq.zipf_frequency(word, "en")


@lru_cache(maxsize=200_000)
def ocr_repair(tok):
    """The word an OCR-confused token stands for, or the token itself."""
    if not tok.strip("il"):
        return tok   # "lll", "iii": Roman numerals as often as not
    variants = set()
    if "ii" in tok:
        variants.add(tok.replace("ii", "ll"))
    for t in [tok, *variants]:
        if t[0] == "l":
            variants.add("i" + t[1:])
        elif t[0] == "i" and len(t) > 1:
            variants.add("l" + t[1:])
    if not variants:
        return tok
    best = max(sorted(variants), key=_zipf)
    z = _zipf(best)
    if z >= OCR_MIN_ZIPF and z - _zipf(tok) >= OCR_MIN_ZIPF_GAIN:
        return best
    return tok


def count_words_repaired(text):
    """(word counts, how many tokens were OCR-repaired)."""
    counts = Counter(tokenize(text))
    if sum(counts[m] for m in OCR_MARKERS) < MIN_OCR_MARKERS:
        return counts, 0
    repaired, n_repaired = Counter(), 0
    for tok, n in counts.items():
        fixed = ocr_repair(tok)
        repaired[fixed] += n
        n_repaired += n if fixed != tok else 0
    return repaired, n_repaired


def count_words(text):
    return count_words_repaired(text)[0]
