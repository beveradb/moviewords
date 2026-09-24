import json

import duckdb

from scripts_path import add_scripts_to_path  # noqa: F401


def test_set_corpus_lang_points_at_lang_subtree():
    import rebuild_web_data as rwd
    rwd.set_corpus("all", lang="es")
    assert rwd.IN.parts[-3:] == ("all", "lang", "es")
    assert rwd.OUT.parts[-3:] == ("all", "lang", "es")
    rwd.set_corpus("en")  # reset for other tests


def test_word_key_is_the_raw_word():
    # The R2/Cloudflare edge percent-decodes the request path once before key
    # lookup, so the object key must be the decoded (raw) word - the frontend
    # still percent-encodes it into the URL.
    from rebuild_web_data import _word_key
    assert _word_key("ring") == "ring"
    assert _word_key("don't") == "don't"
    assert _word_key("café") == "café"
    assert _word_key("semi-pro") == "semi-pro"


def test_stage_trends_bakes_line_top_byyear(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    monkeypatch.setattr(rwd, "OUT", tmp_path)
    con = duckdb.connect()
    con.sql("""
        CREATE TABLE word_year (word VARCHAR, year INT, count BIGINT);
        INSERT INTO word_year VALUES
            ('ring', 2001, 104), ('ring', 1952, 40), ('don''t', 1999, 7);
        CREATE TABLE movies (imdb_id VARCHAR, title VARCHAR, year INT,
                             total_words BIGINT);
        INSERT INTO movies VALUES
            ('tt0120737', 'Fellowship', 2001, 11575),
            ('tt0044672', 'Greatest Show', 1952, 9000),
            ('tt1', 'Nineties Film', 1999, 5000);
        CREATE TABLE words_by_movie (imdb_id VARCHAR, word VARCHAR, count BIGINT);
        INSERT INTO words_by_movie VALUES
            ('tt0120737', 'ring', 104), ('tt0044672', 'ring', 40),
            ('tt1', 'don''t', 7),
            ('tt1', 'subthreshold', 3);
    """)
    rwd.stage_trends(con)

    totals = json.loads((tmp_path / "json" / "year-totals.json").read_text())
    assert totals == {"1952": 40, "1999": 7, "2001": 104}

    ring = json.loads((tmp_path / "json" / "trend" / "ring.json").read_text())
    assert ring["line"] == [[1952, 40], [2001, 104]]
    assert ring["top"][0] == ["tt0120737", "Fellowship", 2001, 104, 11575]
    assert ring["byYear"] == [[1952, "tt0044672", "Greatest Show", 40],
                              [2001, "tt0120737", "Fellowship", 104]]

    apo = json.loads((tmp_path / "json" / "trend" / "don't.json").read_text())
    assert apo["line"] == [[1999, 7]]

    # words below the word_year threshold are NOT baked
    assert not (tmp_path / "json" / "trend" / "subthreshold.json").exists()

    films = json.loads((tmp_path / "json" / "year-films.json").read_text())
    assert films == {"1952": 1, "1999": 1, "2001": 1}


def test_write_year_films_counts_films_per_year(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    monkeypatch.setattr(rwd, "OUT", tmp_path)
    con = duckdb.connect()
    con.sql("""
        CREATE TABLE movies (imdb_id VARCHAR, year INT);
        INSERT INTO movies VALUES ('a', 2001), ('b', 2001), ('c', 1952), ('d', NULL);
    """)
    rwd.write_year_films(con)
    films = json.loads((tmp_path / "json" / "year-films.json").read_text())
    assert films == {"1952": 1, "2001": 2}


def test_yearfilms_is_a_registered_stage():
    import rebuild_web_data as rwd
    assert rwd.STAGES["yearfilms"] is rwd.stage_yearfilms
