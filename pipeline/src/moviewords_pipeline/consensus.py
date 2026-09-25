"""Pick a film's subtitle file by content consensus.

An OPUS film folder holds one XML per OpenSubtitles upload. Most are the same
text re-synced to another video release, lightly edited, or with/without
hearing-impaired tags - their word counts barely differ. The harmful ones are
outliers: DVD commentary tracks, a different film filed under this one,
another language, garbage. Size ranking can't see content and tends to pick
exactly those (they are often the largest file), so the count stage
fingerprints every sampled candidate and takes the most typical file of the
largest agreeing cluster. See docs/superpowers/plans/2026-09-24-content-
consensus-selection.md for the study and calibration behind the thresholds.
"""
import math
import statistics

from . import config
from .derive import load_stopwords

STOPWORDS = load_stopwords()
# Film-making vocabulary: commentary tracks and featurettes talk about the
# film instead of in it.
COMMENTARY_WORDS = frozenset(
    "movie movies film films scene scenes shot shots shoot shooting filmed "
    "filming director directors actor actors actress script camera studio "
    "production cast casting audience sequel dvd commentary footage editing "
    "cgi storyboard".split())


def fingerprint(counts, raw_bytes):
    """Compact, JSON-able summary of one candidate file's word counts."""
    tokens = sum(counts.values())
    stop = sum(n for w, n in counts.items() if w in STOPWORDS)
    talk = sum(n for w, n in counts.items() if w in COMMENTARY_WORDS)
    content = sorted(((n, w) for w, n in counts.items() if w not in STOPWORDS),
                     reverse=True)[:config.FINGERPRINT_WORDS]
    return {
        "tokens": tokens,
        "bytes_per_word": raw_bytes / tokens if tokens else None,
        "stop_share": stop / tokens if tokens else 0.0,
        "commentary_rate": 1000 * talk / tokens if tokens else 0.0,
        "vec": {w: n for n, w in content},
    }


def gate(fp):
    """Why this candidate can't be picked, or None if it's usable."""
    if fp["tokens"] < config.MIN_CANDIDATE_TOKENS:
        return "tiny"
    if fp["stop_share"] < config.MIN_STOPWORD_SHARE:
        return "not-english"
    if fp["bytes_per_word"] > config.MAX_BYTES_PER_WORD:
        return "sparse"
    if (fp["commentary_rate"] >= config.COMMENTARY_MIN_RATE
            and fp["bytes_per_word"] < config.COMMENTARY_MAX_BYTES_PER_WORD):
        return "commentary"
    return None


def cosine(a, b):
    dot = sum(n * b.get(w, 0) for w, n in a.items())
    na = math.sqrt(sum(n * n for n in a.values()))
    nb = math.sqrt(sum(n * n for n in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def choose(candidates, runtime_minutes):
    """(zip_name, info) for the best of `candidates`, a best-rank-first list
    of (zip_name, fingerprint); (None, {"reason": "none"}) if nothing parses.

    info: reason (consensus | rank | single | doubled), cluster size, usable
    count, relaxed (every file failed a gate, so gates were dropped), and
    rejected {zip_name: gate}."""
    rejected = {name: g for name, fp in candidates if (g := gate(fp))}
    usable = [(n, fp) for n, fp in candidates if n not in rejected]
    relaxed = False
    if not usable:
        usable = [(n, fp) for n, fp in candidates if fp["tokens"] > 0]
        relaxed = True
    if not usable:
        return None, {"reason": "none"}
    info = {"usable": len(usable), "relaxed": relaxed, "rejected": rejected}

    if len(usable) == 1:
        return usable[0][0], info | {"reason": "single", "cluster": 1}

    # Group near-identical files (re-uploads, re-syncs) into one TEXT: a
    # wrong file uploaded three times must not outvote genuine translations
    # that merely agree with each other (Baahubali 2).
    texts = []   # [representative fingerprint, [(name, fp), ...]], rank order
    for n, fp in usable:
        for rep, members in texts:
            if cosine(fp["vec"], rep["vec"]) >= config.CONSENSUS_DUPLICATE_COSINE:
                members.append((n, fp))
                break
        else:
            texts.append([fp, [(n, fp)]])
    agree = [[j for j, (other, _) in enumerate(texts) if j != i
              and cosine(rep["vec"], other["vec"]) >= config.CONSENSUS_AGREE_COSINE]
             for i, (rep, _) in enumerate(texts)]

    def votes(i):   # (agreeing distinct texts, files they cover); max() keeps rank order on ties
        group = [i, *agree[i]]
        return len(group), sum(len(texts[j][1]) for j in group)
    head = max(range(len(texts)), key=votes)
    if votes(head) == (1, 1):
        # every text stands alone (independent translations): no majority
        # to follow, so the size ranking decides
        return usable[0][0], info | {"reason": "rank", "cluster": 1}
    cluster = [m for j in [head, *agree[head]] for m in texts[j][1]]
    cluster.sort(key=lambda c: [n for n, _ in usable].index(c[0]))   # back to rank order
    median = statistics.median(fp["tokens"] for _, fp in cluster)
    # nearest the median length rejects doubled and partial rips of the
    # same text; rank order breaks ties
    name, fp = min(cluster, key=lambda c: abs(c[1]["tokens"] - median))
    info |= {"reason": "consensus", "cluster": len(cluster)}
    if runtime_minutes and fp["tokens"] / runtime_minutes > config.MAX_COUNTED_WPM:
        # implausibly fast: a cluster member holding about half the words
        # means this pick is two tracks glued together
        for other, ofp in cluster:
            if 0.4 <= ofp["tokens"] / fp["tokens"] <= 0.6:
                return other, info | {"reason": "doubled"}
    return name, info
