"""Build one MPAA rating's scoped input tree from the published all/ parquets +
ratings.parquet (fetch_ratings.py), so rebuild_web_data's trends stage can bake
per-rating trend JSONs. See docs/superpowers/specs/2026-09-24-mpaa-rating-filter-design.md.

  uv run python scripts/build_rating_slice.py --rating r
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

RATING_CODES = ("g", "pg", "pg13", "r", "nc17")

# MPAA ratings began Nov 1968; earlier films only carry later re-release
# ratings, so rated slices exclude them at source (a biased "re-released
# classics" sample otherwise leaks into movies/words_by_movie/word_year and
# the baked trend top/byYear/year-totals/year-films).
RATING_MIN_YEAR = 1968


def build_rating_slice(all_in: Path, out_in: Path, ratings: Path, code: str) -> int:
    if code not in RATING_CODES:
        raise ValueError(f"unknown rating code {code!r}")
    out_in.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql(f"""
        CREATE TABLE movies AS
            SELECT m.* FROM '{all_in}/movies.parquet' m
            JOIN '{ratings}' r USING (imdb_id)
            WHERE r.rating = '{code}' AND m.year >= {RATING_MIN_YEAR};
        CREATE TABLE wc AS
            SELECT w.* FROM '{all_in}/words_by_movie.parquet' w
            WHERE w.imdb_id IN (SELECT imdb_id FROM movies);
    """)
    con.sql(f"COPY movies TO '{out_in}/movies.parquet' (FORMAT parquet)")
    con.sql(f"""
        COPY (SELECT * FROM wc ORDER BY imdb_id, count DESC)
        TO '{out_in}/words_by_movie.parquet' (FORMAT parquet)
    """)
    # no per-rating pre-aggregate exists (unlike word_year_lang), so derive
    # word_year from the slice's own word counts, with the same per-word >=20
    # corpus floor the whole-corpus + language word_year use.
    con.sql(f"""
        COPY (
            SELECT w.word, m.year, SUM(w.count)::BIGINT AS count,
                   COUNT(*)::BIGINT AS movie_count
            FROM wc w JOIN movies m USING (imdb_id)
            WHERE m.year IS NOT NULL
            GROUP BY w.word, m.year
            QUALIFY SUM(SUM(w.count)) OVER (PARTITION BY w.word) >= 20
            ORDER BY w.word, m.year
        ) TO '{out_in}/word_year.parquet' (FORMAT parquet)
    """)
    return con.sql("SELECT COUNT(*) FROM movies").fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rating", required=True, choices=RATING_CODES)
    ap.add_argument("--webdata", default=str(Path(__file__).resolve().parent.parent / "webdata"))
    args = ap.parse_args()
    all_in = Path(args.webdata) / "in" / "all"
    n = build_rating_slice(all_in, all_in / "rating" / args.rating,
                           all_in / "ratings.parquet", args.rating)
    print(f"wrote {n} films for rating {args.rating}")


if __name__ == "__main__":
    main()
