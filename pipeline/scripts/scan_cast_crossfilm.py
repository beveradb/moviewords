"""Find chosen subtitle files that name ANOTHER film's characters.

A subtitle names its own film's characters. Content consensus and the
relative cast rule (consensus.quality_flags) can't see a wrong film that is
its folder's only file, and "names none of its own cast" alone is no
evidence (narrated films, unnamed characters - see docs/DATA-QUALITY.md).
Naming several distinctive cast names of one other film in the corpus is.

For each film's chosen file: which of its top content words (fp["vec"]) are
distinctive cast tokens - in the cast lists of at most --max-films films and
rare as English words (so "frank", "grace", "will" don't count)? Flag the
file when it names at most --max-own tokens of its own cast and at least
--min-other of a single other film's. Read the hits before blocklisting:
remakes, sequels and biopics legitimately share names.

Run after count + credits:
  uv run python scripts/scan_cast_crossfilm.py [--out hits.csv]
Known limitation: the owner has to be in the corpus (with TMDB credits).
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moviewords_pipeline import config, quality  # noqa: E402
from moviewords_pipeline.wordcount import _zipf  # noqa: E402

MAX_FILMS = 3       # a token in more cast lists than this isn't distinctive
MAX_ZIPF = 3.0      # ...nor is a common English word (zipf 3 = 1 per million)
MIN_OTHER = 3
MAX_OWN = 0


def distinctive(casts, max_films=MAX_FILMS, max_zipf=MAX_ZIPF):
    """{token: {imdb_id, ...}} for cast tokens in at most max_films cast
    lists that are rare English words. `casts`: {imdb_id: token set}."""
    owners = defaultdict(set)
    for imdb_id, tokens in casts.items():
        for tok in tokens:
            owners[tok].add(imdb_id)
    return {tok: ids for tok, ids in owners.items()
            if len(ids) <= max_films and _zipf(tok) < max_zipf}


def scan(vecs, casts, min_other=MIN_OTHER, max_own=MAX_OWN, **kw):
    """Hits: dicts (imdb_id, own, other_id, other, tokens) for chosen files
    naming >= min_other distinctive cast tokens of one other film and <=
    max_own of their own. `vecs`: {imdb_id: chosen file's content vector};
    `casts`: {imdb_id: cast token set}."""
    owners = distinctive(casts, **kw)
    hits = []
    for imdb_id, vec in vecs.items():
        own = len(casts.get(imdb_id, frozenset()) & vec.keys())
        if own > max_own:
            continue
        per_film = defaultdict(list)
        for tok in vec:
            for other in owners.get(tok, ()):
                if other != imdb_id:
                    per_film[other].append(tok)
        if not per_film:
            continue
        other, toks = max(per_film.items(), key=lambda kv: len(kv[1]))
        if len(toks) >= min_other:
            hits.append({"imdb_id": imdb_id, "own": own, "other_id": other,
                         "other": len(toks), "tokens": " ".join(sorted(toks))})
    return sorted(hits, key=lambda h: -h["other"])


def load(work):
    vecs, casts = {}, {}
    for path in (work / "counts" / config.LANG).glob("tt*.json"):
        record = json.loads(path.read_text())
        fp = (record.get("fingerprints") or {}).get(record.get("zip_name"))
        if fp:
            vecs[record["imdb_id"]] = fp["vec"]
    for path in (work / "tmdb_credits").glob("tt*.json"):
        tokens = quality.cast_tokens(json.loads(path.read_text()))
        if tokens:
            casts[path.stem] = tokens
    return vecs, casts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=config.WORK_DIR)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--min-other", type=int, default=MIN_OTHER)
    ap.add_argument("--max-own", type=int, default=MAX_OWN)
    args = ap.parse_args()
    vecs, casts = load(args.work)
    hits = scan(vecs, casts, args.min_other, args.max_own)
    print(f"{len(vecs):,} chosen files, {len(casts):,} cast lists: {len(hits)} hits")
    print(Counter(h["other"] for h in hits))
    for h in hits:
        print(f"{h['imdb_id']} names {h['other_id']} x{h['other']} (own {h['own']}): {h['tokens']}")
    if args.out:
        with args.out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["imdb_id", "own", "other_id", "other", "tokens"])
            w.writeheader()
            w.writerows(hits)


if __name__ == "__main__":
    main()
