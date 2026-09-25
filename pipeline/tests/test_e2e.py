import json

import duckdb
import pytest

from moviewords_pipeline import config, corpus_index, counts, curate, derive
from tests.fixtures.make_mini_corpus import build as build_zip
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def data_tree(tmp_path, monkeypatch):
    for name in ("RAW_DIR", "WORK_DIR", "OUT_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.split("_")[0].lower())
        getattr(config, name).mkdir(parents=True)
    # the fixture repeats two sentences 200 times, which the machine-
    # translation style model rightly finds unnatural (see test_quality)
    monkeypatch.setattr(config, "MT_SCORE_MAX", 1.01)
    return tmp_path


def test_full_pipeline_on_fixture_corpus(data_tree, monkeypatch):
    # download stage stand-in: place fixtures where stages expect them
    build_zip(config.RAW_DIR / "opus_en.zip")
    (config.RAW_DIR / "title.basics.tsv.gz").write_bytes(
        (FIX / "mini.basics.tsv.gz").read_bytes())
    (config.RAW_DIR / "title.ratings.tsv.gz").write_bytes(
        (FIX / "mini.ratings.tsv.gz").read_bytes())
    # fixture TMDB cache instead of network
    tmdb_dir = config.WORK_DIR / "tmdb"
    tmdb_dir.mkdir(parents=True)
    (tmdb_dir / "tt0110912.json").write_text(json.dumps(
        {"imdb_id": "tt0110912", "countries": ["US"], "original_language": "en"}))

    curate.run()
    corpus_index.run()
    counts.run()
    derive.run()

    movies = duckdb.sql(f"SELECT * FROM '{config.OUT_DIR / 'movies.parquet'}'").df()
    assert list(movies.imdb_id) == ["tt0110912"]  # only curated+enriched english film
    hot = json.loads((config.OUT_DIR / "json" / "movie" / "tt0110912.json").read_text())
    assert hot["stats"]["total_words"] > 0
    assert (config.OUT_DIR / "json" / "leaderboard-default.json").exists()
    assert (config.OUT_DIR / "report.md").exists()
    wy = duckdb.sql(f"SELECT * FROM '{config.OUT_DIR / 'word_year.parquet'}'").df()
    assert set(wy.columns) == {"word", "year", "count", "movie_count"}

    wordlists = json.loads((config.OUT_DIR / "json" / "wordlists.json").read_text())
    assert set(wordlists) == {"stopwords", "profanity"}
    assert isinstance(wordlists["stopwords"], list) and len(wordlists["stopwords"]) > 0
    assert isinstance(wordlists["profanity"], list) and len(wordlists["profanity"]) > 0

    words_by_movie = duckdb.sql(
        f"SELECT imdb_id, count FROM '{config.OUT_DIR / 'words_by_movie' / 'data.parquet'}'"
    ).fetchall()
    assert words_by_movie == sorted(words_by_movie, key=lambda r: (r[0], -r[1]))

    words_by_word = duckdb.sql(
        f"SELECT word, imdb_id FROM '{config.OUT_DIR / 'words_by_word' / 'data.parquet'}'"
    ).fetchall()
    assert words_by_word == sorted(words_by_word)


def test_signature_artifacts(data_tree, monkeypatch):
    import json
    build_zip(config.RAW_DIR / "opus_en.zip")
    (config.RAW_DIR / "title.basics.tsv.gz").write_bytes(
        (FIX / "mini.basics.tsv.gz").read_bytes())
    (config.RAW_DIR / "title.ratings.tsv.gz").write_bytes(
        (FIX / "mini.ratings.tsv.gz").read_bytes())
    tmdb_dir = config.WORK_DIR / "tmdb"
    tmdb_dir.mkdir(parents=True)
    (tmdb_dir / "tt0110912.json").write_text(json.dumps(
        {"imdb_id": "tt0110912", "countries": ["US"], "original_language": "en"}))
    curate.run(); corpus_index.run(); counts.run(); derive.run()

    decades = json.loads((config.OUT_DIR / "json" / "signature" / "decades.json").read_text())
    assert "1990" in decades
    assert decades["1990"]["movie_count"] == 1
    assert decades["1990"]["total_words"] > 0
    genres = json.loads((config.OUT_DIR / "json" / "signature" / "genres.json").read_text())
    assert {"Crime", "Drama"} <= set(genres)
    assert all(len(v["top"]) > 0 for v in genres.values())


def test_all_corpus_includes_non_english(data_tree, monkeypatch):
    build_zip(config.RAW_DIR / "opus_en.zip")
    (config.RAW_DIR / "title.basics.tsv.gz").write_bytes(
        (FIX / "mini.basics.tsv.gz").read_bytes())
    (config.RAW_DIR / "title.ratings.tsv.gz").write_bytes(
        (FIX / "mini.ratings.tsv.gz").read_bytes())
    tmdb_dir = config.WORK_DIR / "tmdb"
    tmdb_dir.mkdir(parents=True)
    (tmdb_dir / "tt0110912.json").write_text(json.dumps(
        {"imdb_id": "tt0110912", "countries": ["US"], "original_language": "en"}))
    (tmdb_dir / "tt9999999.json").write_text(json.dumps(
        {"imdb_id": "tt9999999", "countries": ["FR"], "original_language": "fr"}))

    curate.run(); corpus_index.run(); counts.run()
    derive.run(corpus="all")
    derive.run()  # en, default

    out_all = config.OUT_DIR / "all"
    movies = duckdb.sql(f"SELECT * FROM '{out_all / 'movies.parquet'}'").df()
    assert sorted(movies.imdb_id) == ["tt0110912", "tt9999999"]
    assert set(movies.original_language) == {"en", "fr"}

    wyl = duckdb.sql(f"SELECT * FROM '{out_all / 'word_year_lang.parquet'}'").df()
    assert set(wyl.columns) == {"word", "year", "lang", "count", "movie_count"}
    assert "fr" in set(wyl.lang)

    hot = json.loads((out_all / "json" / "movie" / "tt9999999.json").read_text())
    assert hot["original_language"] == "fr"

    # the en corpus coexists in the parent dir and still excludes the French film
    en_movies = duckdb.sql(f"SELECT * FROM '{config.OUT_DIR / 'movies.parquet'}'").df()
    assert list(en_movies.imdb_id) == ["tt0110912"]
    assert list(en_movies.original_language) == ["en"]
    assert not (config.OUT_DIR / "json" / "movie" / "tt9999999.json").exists()
    assert not (config.OUT_DIR / "word_year_lang.parquet").exists()


def test_low_quality_film_gets_a_page_but_stays_out_of_aggregates(data_tree, monkeypatch):
    """Policy (2026-09-25): a film whose only subtitle is machine-translated
    or auto-captioned keeps its film page, with a note, but none of its
    words reach trends, leaderboards or signatures."""
    import pyarrow.parquet as pq
    build_zip(config.RAW_DIR / "opus_en.zip")
    (config.RAW_DIR / "title.basics.tsv.gz").write_bytes(
        (FIX / "mini.basics.tsv.gz").read_bytes())
    (config.RAW_DIR / "title.ratings.tsv.gz").write_bytes(
        (FIX / "mini.ratings.tsv.gz").read_bytes())
    tmdb_dir = config.WORK_DIR / "tmdb"
    tmdb_dir.mkdir(parents=True)
    for imdb_id, lang in (("tt0110912", "en"), ("tt9999999", "fr")):
        (tmdb_dir / f"{imdb_id}.json").write_text(json.dumps(
            {"imdb_id": imdb_id, "countries": ["US"], "original_language": lang}))
    curate.run(); corpus_index.run(); counts.run()
    sel_path = config.WORK_DIR / "selection.parquet"
    sel = pq.read_table(sel_path).to_pylist()
    for row in sel:
        if row["imdb_id"] == "tt9999999":
            row["tier"], row["flags"] = "low", '["machine-translated"]'
    import pyarrow as pa
    pq.write_table(pa.Table.from_pylist(sel), sel_path)
    derive.run(corpus="all")

    out = config.OUT_DIR / "all"
    movies = duckdb.sql(f"SELECT imdb_id FROM '{out / 'movies.parquet'}'").fetchall()
    assert movies == [("tt0110912",)]
    flagged = duckdb.sql(f"SELECT imdb_id, quality, quality_flags FROM "
                         f"'{out / 'movies_flagged.parquet'}'").fetchall()
    assert flagged == [("tt9999999", "low", '["machine-translated"]')]
    page = json.loads((out / "json" / "movie" / "tt9999999.json").read_text())
    assert page["quality"] == {"tier": "low", "flags": ["machine-translated"]}
    assert "kenobi" in {row[0] for row in page["top"]}
    assert "quality" not in json.loads((out / "json" / "movie" / "tt0110912.json").read_text())
    # none of its words in the aggregates
    trend_words = {w for (w,) in duckdb.sql(f"SELECT DISTINCT word FROM '{out / 'word_year.parquet'}'").fetchall()}
    assert "kenobi" not in trend_words and "cheese" in trend_words
    board = json.loads((out / "json" / "leaderboard-default.json").read_text())
    assert "kenobi" not in {row[0] for row in board["words"]}
    per_film = {i for (i,) in duckdb.sql(
        f"SELECT DISTINCT imdb_id FROM '{out / 'words_by_movie' / 'data.parquet'}'").fetchall()}
    assert per_film == {"tt0110912"}
    assert "low subtitle quality" in (out / "report.md").read_text()
