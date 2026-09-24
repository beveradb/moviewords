"""Fetch each film's US MPAA certification from TMDB and build
webdata/in/all/ratings.parquet (imdb_id, rating) for the Trends rating filter.

Per film: /find/{imdb_id} -> TMDB id, then /movie/{id}/release_dates. The raw US
release_dates entries are cached per film (resumable + incremental - re-run
after the corpus grows and only new films are fetched). The rating is the
film's ORIGINAL US theatrical certification (re-releases can carry a
different, later certification, which this deliberately ignores).

Run: cd pipeline && uv run python scripts/fetch_ratings.py [--stage fetch|parquet|all]
       [--workers 8] [--cache DIR] [--out PATH] [--data-base https://data.moviewords.org]
Requires TMDB_API_TOKEN or TMDB_API_KEY in the env.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402
import requests  # noqa: E402

from moviewords_pipeline import config  # noqa: E402
from moviewords_pipeline.tmdb import BASE, make_session  # noqa: E402

CACHE = config.WORK_DIR / "tmdb_release"
OUT = Path(__file__).resolve().parents[1] / "webdata" / "in" / "all" / "ratings.parquet"

BUCKETS = {"G": "g", "PG": "pg", "PG-13": "pg13", "R": "r", "NC-17": "nc17", "X": "nc17"}
# theatrical, limited, premiere; every other release type ranks after these
TYPE_RANK = {3: 0, 2: 1, 1: 2}


def pick_certification(us_release_dates):
    """The certification to use from a film's US release_dates entries:
    only entries whose certification maps to an MPAA bucket (G, PG, PG-13,
    R, NC-17, X) are considered - an 'NR'/'TV-MA'/other non-MPAA entry must
    never win over a real MPAA mark on the same film. Among MPAA-mappable
    entries, prefer theatrical, then limited, then premiere, then any type;
    earliest date within the chosen type. None when no entry is MPAA-mappable."""
    cands = [d for d in us_release_dates if bucket(d.get("certification"))]
    if not cands:
        return None
    best = min(cands, key=lambda d: (TYPE_RANK.get(d.get("type"), 9),
                                     d.get("release_date") or "9999"))
    return best["certification"].strip()


def bucket(cert):
    """MPAA mark -> rating code (X folds into nc17); None for NR/unrated/other."""
    return BUCKETS.get((cert or "").strip().upper())


def _get_json(session, url, **params):
    """GET with a short backoff on TMDB rate limiting (429)."""
    for attempt in range(6):
        resp = session.get(url, params=params or None, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def us_release_dates(session, imdb_id):
    """{'tmdb_id': id, 'us': [...]} or None when TMDB has no match."""
    found = _get_json(session, f"{BASE}/find/{imdb_id}", external_source="imdb_id")
    results = found.get("movie_results", [])
    if not results or results[0].get("id") is None:
        return None
    tmdb_id = results[0]["id"]
    data = _get_json(session, f"{BASE}/movie/{tmdb_id}/release_dates")
    us = [r for r in data.get("results", []) if r.get("iso_3166_1") == "US"]
    return {"tmdb_id": tmdb_id, "us": us[0].get("release_dates", []) if us else []}


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        _local.s = make_session()
    return _local.s


def fetch_one(imdb_id, cache):
    path = cache / f"{imdb_id}.json"
    if path.exists():
        return "cached"
    try:
        _write_json(path, us_release_dates(_session(), imdb_id))  # 'null' cached too
        return "ok"
    except Exception as exc:  # one film must never kill the batch
        print(f"ratings {imdb_id}: {exc}", flush=True)
        return "failed"


def load_ids(data_base):
    resp = requests.get(f"{data_base}/all/json/movies-index.json", timeout=60)
    resp.raise_for_status()
    return [m["id"] for m in resp.json()]


def fetch_all(ids, cache, workers):
    cache.mkdir(parents=True, exist_ok=True)
    counts = {}
    with ThreadPoolExecutor(workers) as pool:
        for i, status in enumerate(pool.map(lambda x: fetch_one(x, cache), ids), 1):
            counts[status] = counts.get(status, 0) + 1
            if i % 1000 == 0:
                print(f"  {i}/{len(ids)} {counts}", flush=True)
    print(f"fetch done: {counts}", flush=True)
    return counts


def build_parquet(cache, out):
    """ratings.parquet from the raw cache: one row per film with a bucketed
    rating; unrated/unmatched films are omitted. Returns the row count."""
    rows = []
    for path in sorted(Path(cache).glob("*.json")):
        data = json.loads(path.read_text())
        if not data:
            continue
        code = bucket(pick_certification(data.get("us", [])))
        if code:
            rows.append((path.stem, code))
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE r (imdb_id VARCHAR, rating VARCHAR)")
    if rows:
        con.executemany("INSERT INTO r VALUES (?, ?)", rows)
    con.execute(f"COPY (SELECT * FROM r ORDER BY imdb_id) TO '{out}' (FORMAT parquet)")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["fetch", "parquet", "all"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--data-base", default="https://data.moviewords.org")
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    if args.stage in ("fetch", "all"):
        fetch_all(load_ids(args.data_base), cache, args.workers)
    if args.stage in ("parquet", "all"):
        print(f"wrote {build_parquet(cache, out)} rated films -> {out}")


if __name__ == "__main__":
    main()
