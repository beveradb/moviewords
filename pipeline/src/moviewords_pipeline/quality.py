"""Per-file quality features, recorded in each candidate's fingerprint
(fp["q"]) so selection rules can be recalibrated without re-reading files.

Calibrated 2026-09-25 on the pre-1968 "fuck" audit (39 English-original
films read line by line) plus ~1,000 random files; see
docs/superpowers/plans/2026-09-25-subtitle-quality.md. What they catch:

- Auto-generated captions (YouTube ASR): unpunctuated run-on blocks of
  18-24 tokens a line, most lines lower-case. Normal files: ~5 tokens a
  line (p99 9), 99% of lines capitalised.
- Machine-translated English (back-translated from another language's
  subtitles): locally fluent, so n-gram and vocabulary-era scores miss
  it, but its function-word profile is distinctive (overused "not", "do",
  "will", "but", uncontracted forms; underused "there's", "'s"). The
  `style` counts feed a logistic model (bt_model_en.json).
- OPUS's own machine_translated flag (rare, but decisive when set).
- Debris from other scripts / mis-decoded text.
"""
import json
import math
import re
from functools import cache
from importlib import resources

PUNCT_RE = re.compile(r"[.,!?;:…]")
END_PUNCT_RE = re.compile(r"[.!?…:;,\"'”»\-–—)]\s*$")
# letters outside Latin (incl. extended Latin) and general punctuation:
# Cyrillic, Greek, CJK, Arabic... left in an "English" file
NON_LATIN_RE = re.compile(r"[^\x00-ɏ -⁯♪♫]")
# UTF-8 read as Latin-1: "Ã©", "â€™"
MOJIBAKE_RE = re.compile(r"Ã.|â€")
MT_FLAG_RE = re.compile(rb"<machine_translated>\s*(\d)\s*<")
CONTRACTION_SUFFIXES = ("n't", "'s", "'re", "'ll", "'m", "'ve", "'d")


@cache
def profanity_words():
    from .derive import load_profanity
    return frozenset(load_profanity())


@cache
def style_words():
    text = resources.files("moviewords_pipeline").joinpath("style_words_en.txt").read_text()
    return tuple(w.strip() for w in text.splitlines()
                 if w.strip() and not w.startswith("#"))


def machine_translated_flag(raw):
    """OPUS's <machine_translated> 0/1 from the file's <meta> block (at the
    end of the XML), or None when the file has no such field (the newer
    uploads' minimal metadata)."""
    m = MT_FLAG_RE.search(raw[raw.rfind(b"<meta"):]) if b"<meta" in raw else None
    return int(m.group(1)) if m else None


def features(raw, text, counts, ocr_repaired=0):
    """JSON-able quality features of one subtitle file: `raw` its XML
    bytes, `text` the parsed dialogue (one line per subtitle sentence),
    `counts` its word counts, `ocr_repaired` how many tokens the counting
    repaired (see wordcount.count_words_repaired)."""
    lines = [line for line in text.split("\n") if line.strip()]
    tokens = sum(counts.values())
    n_lines = len(lines) or 1
    letters = sum(ch.isalpha() for ch in text) or 1
    style = {w: counts[w] for w in style_words() if counts.get(w)}
    for suffix in CONTRACTION_SUFFIXES:
        n = sum(v for w, v in counts.items() if w.endswith(suffix))
        if n:
            style["*" + suffix] = n
    return {
        "lines": len(lines),
        "toks_per_line": round(tokens / n_lines, 3),
        "cap_start": round(sum(line.lstrip("-–\"' ")[:1].isupper()
                               for line in lines) / n_lines, 4),
        "end_punct": round(sum(bool(END_PUNCT_RE.search(line))
                               for line in lines) / n_lines, 4),
        "punct_per_tok": round(len(PUNCT_RE.findall(text)) / (tokens or 1), 4),
        "non_latin_k": round(1000 * len(NON_LATIN_RE.findall(text)) / letters, 3),
        "mojibake_k": round(1000 * len(MOJIBAKE_RE.findall(text)) / letters, 3),
        "ocr_repaired_k": round(1000 * ocr_repaired / (tokens or 1), 3),
        "mt": machine_translated_flag(raw),
        "style": style,
        # rare words drop out of the content vector; the swearing canary
        # (anachronistic profanity) needs them per file
        "profanity": {w: n for w, n in counts.items() if w in profanity_words()},
    }


STRONG_PROFANITY_RE = re.compile(r"^(mother)?fuck|^cunt")


def strong_profanity(q):
    """How many times the file says fuck/motherfucker/cunt (any form)."""
    return sum(n for w, n in q.get("profanity", {}).items() if STRONG_PROFANITY_RE.match(w))


def is_asr(q):
    """Auto-generated captions: long unpunctuated, mostly lower-case lines."""
    return (q["toks_per_line"] >= 12 and q["cap_start"] < 0.75
            and q["end_punct"] < 0.6)


@cache
def _bt_model():
    return json.loads(resources.files("moviewords_pipeline")
                      .joinpath("bt_model_en.json").read_text())


def style_vector(style, tokens, names):
    """Rates per 1k tokens of `names` (style words, then "*n't" etc.), plus
    the n't / (n't + not) contraction ratio."""
    total = tokens or 1
    x = [1000 * style.get(w, 0) / total for w in names]
    nt, nots = style.get("*n't", 0), style.get("not", 0)
    x.append(nt / (nt + nots + 1))
    return x


def mt_score(q, tokens):
    """Probability (0-1) that a file is machine-translated English, from its
    function-word profile. None when the file is too short to judge."""
    if tokens < 1000:
        return None
    model = _bt_model()
    x = style_vector(q["style"], tokens, model["features"])
    z = model["intercept"] + sum(
        c * (v - m) / s for c, v, m, s in zip(model["coef"], x, model["mean"], model["std"]))
    return 1 / (1 + math.exp(-z))


# --- cast-name check -------------------------------------------------------
# A subtitle names its film's characters; a wrong film filed under this id
# names another film's.
SELF_ROLES = re.compile(r"^(him|her|them)sel(f|ves)\b|^self\b|^narrator\b|^various\b", re.I)
PARENS_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
NAME_TOKEN_RE = re.compile(r"[a-z]{3,}")


def cast_tokens(credits):
    """Lower-case name tokens (non-stopwords, 3+ letters) from a
    tmdb_credits record: each character's name, or the actor's when they
    play themselves (documentaries). Empty for None (no TMDB match). Only
    good for comparing one candidate file with another: a genuine file can
    name none of them (narrated films, unnamed characters, TMDB listing
    role descriptions), so naming none is no evidence on its own."""
    if not credits:
        return frozenset()
    import unicodedata
    from .derive import load_stopwords
    stop = load_stopwords()
    out = set()
    for character, actor in zip(credits.get("characters") or [], credits.get("actors") or []):
        name = PARENS_RE.sub(" ", character or "").strip()
        if not name or SELF_ROLES.match(name):
            name = actor or ""
        name = unicodedata.normalize("NFKD", name.lower())
        name = "".join(ch for ch in name if not unicodedata.combining(ch))
        out.update(tok for tok in NAME_TOKEN_RE.findall(name) if tok not in stop)
    return frozenset(out)


def cast_hits(fp, tokens):
    """How many of the film's cast name tokens this file uses often enough
    to be among its top content words."""
    return len(tokens & fp["vec"].keys())
