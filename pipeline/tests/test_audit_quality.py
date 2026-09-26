import json

import duckdb

from scripts_path import add_scripts_to_path  # noqa: F401


def _work(tmp_path, films, words):
    """A minimal data/work: films = [(imdb_id, title, year, genres, lang, tier, wpm)],
    words = [(imdb_id, word, count)]."""
    con = duckdb.connect()
    con.sql("CREATE TABLE f (imdb_id VARCHAR, title VARCHAR, year INT, genres VARCHAR[], "
            "lang VARCHAR, tier VARCHAR, wpm DOUBLE)")
    con.executemany("INSERT INTO f VALUES (?, ?, ?, ?, ?, ?, ?)", films)
    con.sql("CREATE TABLE w (imdb_id VARCHAR, word VARCHAR, count INT)")
    if words:
        con.executemany("INSERT INTO w VALUES (?, ?, ?)", words)
    for name, sql in {
        "selection": "SELECT imdb_id, tier, '[]' AS flags, 'single' AS reason, 'x.xml' AS zip_name FROM f",
        "curated": "SELECT imdb_id, title, year, genres, 90 AS runtime_minutes FROM f",
        "movie_stats": "SELECT imdb_id, 9000 AS total_words, wpm AS words_per_minute FROM f",
        "word_counts": "SELECT * FROM w",
    }.items():
        con.sql(f"COPY ({sql}) TO '{tmp_path / name}.parquet' (FORMAT parquet)")
    (tmp_path / "tmdb").mkdir()
    for imdb_id, *_, lang, _tier, _wpm in films:
        (tmp_path / "tmdb" / f"{imdb_id}.json").write_text(
            json.dumps({"imdb_id": imdb_id, "original_language": lang}))
    return tmp_path


def test_profanity_canary_covers_the_whole_family(tmp_path):
    import audit_quality
    work = _work(tmp_path, [
        ("tt0000001", "Studio Western", 1947, ["Western"], "en", "ok", 90.0),
        ("tt0000002", "Epic", 1956, ["Drama"], "en", "ok", 90.0),
        ("tt0054763", "The Connection", 1961, ["Drama"], "en", "ok", 90.0),
        ("tt0000004", "Low", 1950, ["Drama"], "en", "low", 90.0),
        ("tt0000005", "Later", 1975, ["Drama"], "en", "ok", 90.0),
    ], [
        ("tt0000001", "shit", 1), ("tt0000001", "shithead", 1),
        ("tt0000002", "shittim", 3),
        ("tt0054763", "shit", 9), ("tt0054763", "bullshit", 1),
        ("tt0000004", "fuck", 5), ("tt0000005", "fuck", 5),
    ])
    rows = {r["imdb_id"]: r for r in audit_quality.profanity(audit_quality.connect(work))}
    assert set(rows) == {"tt0000001", "tt0054763"}
    assert rows["tt0000001"]["hits"] == 2 and not rows["tt0000001"]["verified"]
    assert rows["tt0054763"]["verified"] is True


def test_silent_rate_canary_lists_silents_at_talkie_rates(tmp_path):
    import audit_quality
    work = _work(tmp_path, [
        ("tt0018379", "7th Heaven", 1927, ["Drama"], "en", "ok", 59.0),
        ("tt0018455", "Sunrise", 1927, ["Drama"], "en", "ok", 4.0),
        ("tt0019096", "Lights of New York", 1928, ["Crime"], "en", "ok", 92.4),
    ], [])
    rows = audit_quality.silent_rates(audit_quality.connect(work))
    assert [r["imdb_id"] for r in rows] == ["tt0018379"]
