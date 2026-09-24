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
