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

from . import config, quality
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


# gate() verdicts that mean the file is not this film's dialogue at all:
# never relaxed - a film whose every file fails one is dropped. "tiny" and
# "sparse" do relax: when every upload is tiny the film is near-wordless
# (Silent Movie says one word, The Red Turtle none) and when every upload
# is sparse it's a musical (lyrics are stripped).
HARD_GATES = frozenset({"not-english", "commentary"})


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


def quality_flags(pool, cast=None):
    """{zip_name: [flags]} for (zip_name, fingerprint) pairs: "asr"
    (auto-captions), "machine-translated" (OPUS flag or style model),
    "wrong-cast" (names none of the film's characters while another file
    does, or - with plenty of distinctive names to look for - names none
    at all). `cast` is {"strict": tokens, "broad": tokens} or None."""
    flags = {name: [] for name, _ in pool}
    for name, fp in pool:
        q = fp.get("q")
        if not q:
            continue   # fingerprint from before quality features
        if quality.is_asr(q):
            flags[name].append("asr")
        score = quality.mt_score(q, fp["tokens"])
        if q["mt"] == 1 or (score is not None and score >= config.MT_SCORE_MAX):
            flags[name].append("machine-translated")
    if cast:
        broad = {name: quality.cast_hits(fp, cast["broad"]) for name, fp in pool}
        best = max(broad.values(), default=0)
        for name, fp in pool:
            if broad[name]:
                continue
            if best >= config.CAST_MIN_HITS or (
                    len(cast["strict"]) >= config.CAST_MIN_STRICT_TOKENS
                    and not quality.cast_hits(fp, cast["strict"])):
                flags[name].append("wrong-cast")
    return flags


def choose(candidates, runtime_minutes, cast=None):
    """(zip_name, info) for the best of `candidates`, a best-rank-first list
    of (zip_name, fingerprint); (None, info) if none is this film's dialogue
    - info["reason"] "none" when nothing parses, "dropped" when every file
    fails a hard gate (commentary, other language).

    info: reason (consensus | rank | single | doubled), cluster size, usable
    count, relaxed (every file was tiny or sparse - near-wordless films,
    musicals - so those gates were dropped), rejected {zip_name: gate}, tier ("ok", or "low" when every
    usable file has quality flags and the least bad was kept), flags (the
    chosen file's quality flags) and flagged {zip_name: flags} for files
    passed over."""
    rejected = {name: g for name, fp in candidates if (g := gate(fp))}
    readable = [(n, fp) for n, fp in candidates if fp["tokens"] > 0]
    if not readable:
        return None, {"reason": "none"}
    pool = [(n, fp) for n, fp in readable if n not in rejected]
    relaxed = False
    if not pool:
        pool = [(n, fp) for n, fp in readable if rejected[n] not in HARD_GATES]
        relaxed = True
    if not pool:
        return None, {"reason": "dropped", "rejected": rejected, "tier": "drop",
                      "flags": [], "flagged": {}}
    flags = quality_flags(pool, cast)
    usable = [(n, fp) for n, fp in pool if not flags[n]]
    tier = "ok"
    if not usable:
        usable, tier = pool, "low"
    info = {"usable": len(usable), "relaxed": relaxed, "rejected": rejected,
            "tier": tier, "flagged": {n: f for n, f in flags.items() if f}}
    name, info = _consensus(usable, runtime_minutes, info)
    info["flags"] = flags[name]
    if tier == "ok":
        info["flagged"] = {n: f for n, f in info["flagged"].items() if n != name}
    return name, info


def _consensus(usable, runtime_minutes, info):
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
