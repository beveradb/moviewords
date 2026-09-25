import json

import duckdb

from scripts_path import add_scripts_to_path  # noqa: F401


def test_stage_words_writes_every_word_with_counts_and_film_frequency(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    wbm = tmp_path / "words_by_movie.parquet"
    duckdb.sql(f"""
        COPY (SELECT * FROM (VALUES
            ('tt1', 'shiiiit', 1), ('tt1', 'oh', 11), ('tt1', 'butch', 34), ('tt1', 'aa', 11),
            ('tt2', 'oh', 3), ('tt2', 'zed', 2))
            t(imdb_id, word, count)
            ORDER BY imdb_id, count DESC)
        TO '{wbm}' (FORMAT parquet)
    """)
    monkeypatch.setattr(rwd, "IN", tmp_path)
    monkeypatch.setattr(rwd, "OUT", tmp_path / "out")
    con = duckdb.connect()
    con.sql(f"CREATE VIEW words_by_movie AS SELECT * FROM '{wbm}'")
    rwd.stage_words(con)

    tt1 = json.loads((tmp_path / "out" / "json" / "words" / "tt1.json").read_text())
    # count desc, then word asc for ties; films = corpus document frequency
    assert tt1 == {"w": [["butch", 34, 1], ["aa", 11, 1], ["oh", 11, 2], ["shiiiit", 1, 1]]}
    tt2 = json.loads((tmp_path / "out" / "json" / "words" / "tt2.json").read_text())
    assert tt2 == {"w": [["oh", 3, 2], ["zed", 2, 1]]}
    assert "words" in rwd.STAGES


def test_flagged_films_get_movie_and_word_pages_from_their_own_parquets(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    for name, rows in (("words_by_movie", "('tt1', 'oh', 11), ('tt1', 'butch', 34)"),
                       ("words_by_movie_flagged", "('tt9', 'oh', 5), ('tt9', 'kenobi', 3)")):
        duckdb.sql(f"COPY (SELECT * FROM (VALUES {rows}) t(imdb_id, word, count) "
                   f"ORDER BY imdb_id, count DESC) TO '{tmp_path / name}.parquet' (FORMAT parquet)")
    cols = "t(imdb_id, title, year, total_words, unique_words, words_per_minute)"
    duckdb.sql(f"COPY (SELECT * FROM (VALUES ('tt1', 'Pulp', 1994, 45, 2, 0.3::DOUBLE)) {cols}) "
               f"TO '{tmp_path / 'movies.parquet'}' (FORMAT parquet)")
    duckdb.sql(f"COPY (SELECT *, 'low' AS quality, '[\"machine-translated\"]' AS quality_flags "
               f"FROM (VALUES ('tt9', 'Arizona', 1931, 8, 2, 0.1::DOUBLE)) {cols}) "
               f"TO '{tmp_path / 'movies_flagged.parquet'}' (FORMAT parquet)")
    duckdb.sql(f"COPY (SELECT 'oh' AS word, 0.0::DOUBLE AS zipf, 'x' AS classes, 'x' AS pos, 0.0::DOUBLE AS dist) "
               f"TO '{tmp_path / 'wm.parquet'}' (FORMAT parquet)")
    monkeypatch.setattr(rwd, "IN", tmp_path)
    monkeypatch.setattr(rwd, "OUT", tmp_path / "out")
    (tmp_path / "out").mkdir()
    (tmp_path / "wm.parquet").rename(tmp_path / "out" / "word_meta.parquet")
    con = duckdb.connect()
    con.sql(f"CREATE VIEW movies AS SELECT * FROM '{tmp_path / 'movies.parquet'}'")
    con.sql(f"CREATE VIEW words_by_movie AS SELECT * FROM '{tmp_path / 'words_by_movie.parquet'}'")
    rwd.stage_movies(con)
    rwd.stage_words(con)
    page = json.loads((tmp_path / "out" / "json" / "movie" / "tt9.json").read_text())
    assert page["quality"] == {"tier": "low", "flags": ["machine-translated"]}
    assert "quality" not in json.loads((tmp_path / "out" / "json" / "movie" / "tt1.json").read_text())
    words = json.loads((tmp_path / "out" / "json" / "words" / "tt9.json").read_text())
    # the corpus films plus itself; it adds nothing to the corpus films' counts
    assert words == {"w": [["oh", 5, 2], ["kenobi", 3, 1]]}
    tt1 = json.loads((tmp_path / "out" / "json" / "words" / "tt1.json").read_text())
    assert tt1 == {"w": [["butch", 34, 1], ["oh", 11, 1]]}
