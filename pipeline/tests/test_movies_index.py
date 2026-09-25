import json

import duckdb

from scripts_path import add_scripts_to_path  # noqa: F401  (see step 2)


def test_build_movies_index(tmp_path):
    from build_movies_index import build
    src = tmp_path / "movies.parquet"
    duckdb.sql("""
        SELECT * FROM (VALUES
            ('tt1', 'Big Hit', 1999, 8.1, 900000, 12000, 3000,
             ['Drama'], 'en'),
            ('tt2', 'Petit Film', 2001, 7.0, 450, 6000, 2000,
             ['Comedy'], 'fr')
        ) t(imdb_id, title, year, rating, votes, total_words, unique_words,
            genres, original_language)
    """).write_parquet(str(src))
    dest = tmp_path / "json" / "movies-index.json"
    n = build(src, dest)
    assert n == 2
    idx = json.loads(dest.read_text())
    assert [m["id"] for m in idx] == ["tt1", "tt2"]  # votes DESC
    assert idx[1] == {"id": "tt2", "title": "Petit Film", "year": 2001,
                      "rating": 7.0, "votes": 450, "total_words": 6000,
                      "unique_words": 2000, "genres": ["Comedy"], "lang": "fr"}


def test_build_movies_index_marks_low_quality_films(tmp_path):
    from build_movies_index import build
    cols = "t(imdb_id, title, year, rating, votes, total_words, unique_words, genres, original_language)"
    src, flagged = tmp_path / "movies.parquet", tmp_path / "movies_flagged.parquet"
    duckdb.sql(f"SELECT * FROM (VALUES ('tt1', 'Big Hit', 1999, 8.1, 900, 12000, 3000, ['Drama'], 'en')) {cols}"
               ).write_parquet(str(src))
    duckdb.sql(f"SELECT *, 'low' AS quality, '[\"asr\"]' AS quality_flags FROM (VALUES "
               f"('tt2', 'Arizona', 1931, 5.9, 387, 5440, 900, ['Western'], 'en')) {cols}"
               ).write_parquet(str(flagged))
    dest = tmp_path / "movies-index.json"
    assert build(src, dest, flagged) == 2
    idx = {m["id"]: m for m in json.loads(dest.read_text())}
    assert "q" not in idx["tt1"] and idx["tt2"]["q"] == "low"
