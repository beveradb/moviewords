"""Build json/movies-index.json - the slim all-movies client-side search
index. Run per corpus after derive:

  uv run python scripts/build_movies_index.py [--corpus en|all]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

from moviewords_pipeline import config  # noqa: E402


COLS = ("imdb_id, title, year, rating, votes, total_words, unique_words, "
        "genres, original_language")


def build(movies_parquet, dest, flagged_parquet=None):
    """Films in `movies_parquet`, plus - marked "q": "low" - the films derive
    kept out of the aggregates for low subtitle quality, so search still
    finds their pages. Client code that counts or ranks films must skip
    entries with "q"."""
    flagged = ""
    if flagged_parquet and flagged_parquet.exists():
        flagged = f"UNION ALL SELECT {COLS}, 'low' FROM '{flagged_parquet}'"
    rows = duckdb.sql(f"""
        SELECT * FROM (SELECT {COLS}, NULL AS q FROM '{movies_parquet}' {flagged})
        ORDER BY votes DESC, imdb_id
    """).fetchall()
    out = [{"id": r[0], "title": r[1], "year": r[2], "rating": float(r[3]),
            "votes": r[4], "total_words": r[5], "unique_words": r[6],
            "genres": r[7], "lang": r[8]} | ({"q": r[9]} if r[9] else {})
           for r in rows]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out))
    return len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="en", choices=["en", "all"])
    args = ap.parse_args()
    out = config.OUT_DIR if args.corpus == "en" else config.OUT_DIR / "all"
    n = build(out / "movies.parquet", out / "json" / "movies-index.json",
              out / "movies_flagged.parquet")
    print(f"wrote {n} entries ({args.corpus})")


if __name__ == "__main__":
    main()
