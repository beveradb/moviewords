"""Fetch movie posters from TMDB into data/out/posters/<imdb_id>.jpg, then
encode each to a sibling <imdb_id>.avif (see encode_posters.py).

Self-hosting posters in R2 keeps the site independent of TMDB's CDN (and spares
it our traffic). Resumable: existing files are skipped, so re-runs only fetch
what's missing. Requires TMDB_API_TOKEN (v4) or TMDB_API_KEY (v3) in the env.

Run: cd pipeline && uv run python scripts/fetch_posters.py [--size w342] [--workers 8]
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402
import requests  # noqa: E402

from moviewords_pipeline import config  # noqa: E402
from moviewords_pipeline.tmdb import BASE, make_session  # noqa: E402
from encode_posters import encode_all  # noqa: E402

IMG_BASE = "https://image.tmdb.org/t/p"


def fetch_one(session, imdb_id, dest_dir, size):
    dest = dest_dir / f"{imdb_id}.jpg"
    if dest.exists():
        return "cached"
    try:
        found = session.get(f"{BASE}/find/{imdb_id}",
                            params={"external_source": "imdb_id"}, timeout=30)
        found.raise_for_status()
        results = found.json().get("movie_results", [])
        poster_path = results[0].get("poster_path") if results else None
        if not poster_path:
            return "no-poster"
        img = requests.get(f"{IMG_BASE}/{size}{poster_path}", timeout=60)
        img.raise_for_status()
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(img.content)
        tmp.rename(dest)
        return "fetched"
    except Exception as exc:  # never let one movie kill the batch
        print(f"poster {imdb_id}: {exc}", flush=True)
        return "failed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="w342")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    dest_dir = config.OUT_DIR / "posters"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # the all-films corpus is a superset of the English-originals one
    movies = config.OUT_DIR / "all" / "movies.parquet"
    if not movies.exists():
        movies = config.OUT_DIR / "movies.parquet"
    ids = [r[0] for r in duckdb.sql(f"SELECT imdb_id FROM '{movies}'").fetchall()]
    session = make_session()

    tally = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, outcome in enumerate(
                pool.map(lambda m: fetch_one(session, m, dest_dir, args.size), ids)):
            tally[outcome] = tally.get(outcome, 0) + 1
            if (i + 1) % 1000 == 0:
                print(f"{i + 1}/{len(ids)} {tally}", flush=True)
    print(f"done: {tally}")
    print(f"avif: {encode_all(dest_dir)}")


if __name__ == "__main__":
    main()
