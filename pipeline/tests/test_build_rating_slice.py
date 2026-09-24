import duckdb
import pytest

from scripts_path import add_scripts_to_path  # noqa: F401


def _fixture(tmp_path):
    all_in = tmp_path / "in" / "all"
    all_in.mkdir(parents=True)
    con = duckdb.connect()
    con.sql(f"""
        COPY (SELECT * FROM (VALUES
            ('tt1', 'A', 1990, 1000), ('tt2', 'B', 1990, 900),
            ('tt3', 'C', 1995, 800), ('tt4', 'D', 1995, 700),
            ('tt5', 'E', 1939, 600))
            t(imdb_id, title, year, total_words))
        TO '{all_in}/movies.parquet' (FORMAT parquet);
        COPY (SELECT * FROM (VALUES
            ('tt1', 'fuck', 15), ('tt2', 'fuck', 10), ('tt3', 'fuck', 30),
            ('tt1', 'rare', 5), ('tt4', 'fuck', 99), ('tt5', 'fuck', 50))
            t(imdb_id, word, count))
        TO '{all_in}/words_by_movie.parquet' (FORMAT parquet);
        COPY (SELECT * FROM (VALUES
            ('tt1', 'r'), ('tt2', 'r'), ('tt3', 'r'), ('tt4', 'pg'), ('tt5', 'r'))
            t(imdb_id, rating))
        TO '{all_in}/ratings.parquet' (FORMAT parquet);
    """)
    return all_in


def test_build_rating_slice_filters_films_and_rederives_word_year(tmp_path):
    from build_rating_slice import build_rating_slice
    all_in = _fixture(tmp_path)
    out_in = all_in / "rating" / "r"
    n = build_rating_slice(all_in, out_in, all_in / "ratings.parquet", "r")
    # tt5 (1939, pre-1968) is excluded even though it's rated 'r'
    assert n == 3
    assert duckdb.sql(f"SELECT imdb_id FROM '{out_in}/movies.parquet' ORDER BY 1").fetchall() == \
        [("tt1",), ("tt2",), ("tt3",)]
    assert duckdb.sql(f"SELECT count(*) FROM '{out_in}/words_by_movie.parquet'").fetchone()[0] == 4
    # 'rare' (total 5) is under the >=20 floor; 'fuck' kept with per-year sums + film counts
    assert duckdb.sql(
        f"SELECT word, year, count, movie_count FROM '{out_in}/word_year.parquet' ORDER BY word, year"
    ).fetchall() == [("fuck", 1990, 25, 2), ("fuck", 1995, 30, 1)]


def test_build_rating_slice_rejects_unknown_code(tmp_path):
    from build_rating_slice import build_rating_slice
    all_in = _fixture(tmp_path)
    with pytest.raises(ValueError):
        build_rating_slice(all_in, all_in / "rating" / "x", all_in / "ratings.parquet", "x")


def test_set_corpus_rating_points_at_rating_subtree():
    import rebuild_web_data as rwd
    rwd.set_corpus("all", rating="pg13")
    assert rwd.IN.parts[-3:] == ("all", "rating", "pg13")
    assert rwd.OUT.parts[-3:] == ("all", "rating", "pg13")
    rwd.set_corpus("en")  # reset for other tests


def test_set_corpus_rejects_lang_and_rating_together():
    import rebuild_web_data as rwd
    with pytest.raises(ValueError):
        rwd.set_corpus("all", lang="es", rating="pg13")
    rwd.set_corpus("en")  # reset for other tests
