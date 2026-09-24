"""Detect subtitle files published under the wrong IMDb id.

Stage 1: candidate pairs - films sharing >= min_shared of their top-30 RARE
words (document frequency 2-20). Character names and invented words are
rare; two films sharing many of them almost always share subtitle content.
Stage 2: cosine similarity on the full count vectors. >= 0.95 means the two
films published the same underlying subtitle - one id is wrong.
Stage 3 (--adjudicate): directory consensus. For each member of a duplicate
pair, count every OPUS candidate in its directory and measure how many agree
(cosine >= 0.8) with the file the pipeline chose. The mislabeled member is
the one whose own directory disagrees with its chosen file; the unanimous
directory is the true owner. Suggests blocklist lines for
moviewords_pipeline/mislabeled_subs.txt.

Run after the count stage:
  uv run python scripts/scan_mislabels.py [--adjudicate] [--min-cosine 0.95]
Known limitation: only catches duplicates where BOTH ids are in the corpus.
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

from moviewords_pipeline import config, opus_zip  # noqa: E402
from moviewords_pipeline.corpus_index import imdb_id_from_path  # noqa: E402
from moviewords_pipeline.subtitle_parser import extract_text  # noqa: E402
from moviewords_pipeline.wordcount import count_words  # noqa: E402


def cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(c * b.get(w, 0) for w, c in a.items())
    na = math.sqrt(sum(c * c for c in a.values()))
    nb = math.sqrt(sum(c * c for c in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def find_suspect_pairs(con, min_shared=8):
    """Pairs of films sharing >= min_shared of their top-30 rare words.
    Expects a view/table `wc` with (imdb_id, word, count)."""
    con.sql("""
        CREATE OR REPLACE TEMP TABLE _top_rare AS
        SELECT imdb_id, word FROM (
            SELECT wc.imdb_id, wc.word,
                   ROW_NUMBER() OVER (PARTITION BY wc.imdb_id
                                      ORDER BY wc.count DESC) AS rn
            FROM wc
            JOIN (SELECT word, COUNT(DISTINCT imdb_id) AS films
                  FROM wc GROUP BY word) df USING (word)
            WHERE df.films BETWEEN 2 AND 20 AND wc.count >= 10
        ) WHERE rn <= 30
    """)
    return con.sql(f"""
        SELECT a.imdb_id, b.imdb_id, COUNT(*) AS shared
        FROM _top_rare a JOIN _top_rare b
          ON a.word = b.word AND a.imdb_id < b.imdb_id
        GROUP BY 1, 2 HAVING COUNT(*) >= {int(min_shared)}
        ORDER BY shared DESC
    """).fetchall()


def pick_victim(consensus_a, consensus_b):
    """Index (0/1) of the mislabeled pair member, or None if ambiguous.
    The victim's own directory disagrees with its chosen file (low
    consensus); the owner's directory is self-consistent (high)."""
    if consensus_a >= 0.8 and consensus_b < 0.5:
        return 1
    if consensus_b >= 0.8 and consensus_a < 0.5:
        return 0
    return None


def _vectors(con, ids):
    ph = ", ".join(f"'{i}'" for i in ids)
    vecs = defaultdict(dict)
    for imdb_id, word, count in con.sql(
            f"SELECT imdb_id, word, count FROM wc WHERE imdb_id IN ({ph})").fetchall():
        vecs[imdb_id][word] = count
    return vecs


def _directory_consensus(z, imdb_id, chosen_name, chosen_counts):
    """[(zip_name, tokens, cos_vs_chosen)] for every candidate in the film's
    OPUS dir, plus the fraction of OTHER candidates agreeing with the chosen
    file (empty dir of siblings -> 1.0, can't convict)."""
    rows, agree, others = [], 0, 0
    for info in z.infolist():
        if imdb_id_from_path(info.filename) != imdb_id:
            continue
        counts = count_words(extract_text(z.read(info.filename)))
        cos = cosine(counts, chosen_counts)
        rows.append((info.filename, sum(counts.values()), cos))
        if info.filename != chosen_name:
            others += 1
            agree += cos >= 0.8
    return rows, (agree / others if others else 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjudicate", action="store_true")
    ap.add_argument("--min-cosine", type=float, default=0.95)
    ap.add_argument("--min-shared", type=int, default=8)
    args = ap.parse_args()

    w = config.WORK_DIR
    con = duckdb.connect()
    con.sql(f"CREATE VIEW wc AS SELECT * FROM '{w / 'word_counts.parquet'}'")
    titles = dict((r[0], f"{r[1]} ({r[2]})") for r in con.sql(
        f"SELECT imdb_id, title, year FROM '{w / 'curated.parquet'}'").fetchall())
    chosen = dict(con.sql(
        f"SELECT imdb_id, zip_name FROM '{w / 'corpus_index.parquet'}'").fetchall())

    pairs = find_suspect_pairs(con, args.min_shared)
    print(f"stage 1: {len(pairs)} candidate pairs (>= {args.min_shared} shared rare words)")
    ids = sorted({i for a, b, _ in pairs for i in (a, b)})
    # the file actually counted: the count stage may have swapped the index's
    # pick for an alternate (cache record `zip_name` vs `indexed_as`)
    for imdb_id in ids:
        cache = w / "counts" / config.LANG / f"{imdb_id}.json"
        if cache.exists():
            chosen[imdb_id] = json.loads(cache.read_text()).get("zip_name", chosen[imdb_id])
    vecs = _vectors(con, ids) if ids else {}

    duplicates, review = [], []
    for a, b, shared in pairs:
        cos = cosine(vecs[a], vecs[b])
        (duplicates if cos >= args.min_cosine else review).append((cos, shared, a, b))
    for label, bucket in (("DUPLICATE", duplicates), ("review", review)):
        for cos, shared, a, b in sorted(bucket, reverse=True):
            print(f"  {label:9s} cos={cos:.3f} shared={shared:2d} "
                  f"{a} {titles.get(a, '?')} | {b} {titles.get(b, '?')}")

    if not args.adjudicate or not duplicates:
        return
    print("\nstage 3: directory consensus for DUPLICATE pairs")
    with opus_zip.open_source() as z:
        for cos, shared, a, b in sorted(duplicates, reverse=True):
            cons = {}
            for m in (a, b):
                rows, consensus = _directory_consensus(z, m, chosen[m], vecs[m])
                cons[m] = consensus
                print(f"\n  {m} {titles.get(m, '?')} chosen={chosen[m]} "
                      f"sibling-consensus={consensus:.2f}")
                for name, tokens, c in sorted(rows, key=lambda r: -r[2]):
                    marker = "*" if name == chosen[m] else " "
                    print(f"   {marker} cos={c:.3f} {tokens:6d}t {name}")
            victim = pick_victim(cons[a], cons[b])
            if victim is None:
                print(f"  VERDICT: manual review - consensus {cons[a]:.2f} vs {cons[b]:.2f}")
            else:
                vid = (a, b)[victim]
                print(f"  VERDICT: {vid} is mislabeled - suggested blocklist line:")
                print(f"    {vid} {chosen[vid]} content matches {(a, b)[1 - victim]}")


if __name__ == "__main__":
    main()
