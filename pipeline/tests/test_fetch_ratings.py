import importlib.util
import json
from pathlib import Path

import duckdb

SPEC = importlib.util.spec_from_file_location(
    "fetch_ratings",
    Path(__file__).resolve().parents[1] / "scripts" / "fetch_ratings.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def rd(cert, typ, date):
    return {"certification": cert, "type": typ, "release_date": date}


def test_pick_prefers_theatrical_over_earlier_other_types():
    dates = [rd("TV-MA", 6, "1990-01-01"), rd("R", 3, "1995-05-01"), rd("PG-13", 4, "1994-01-01")]
    assert mod.pick_certification(dates) == "R"


def test_pick_falls_back_through_limited_then_premiere_then_any():
    assert mod.pick_certification([rd("PG", 1, "2000-01-01"), rd("R", 2, "2001-01-01")]) == "R"
    assert mod.pick_certification([rd("PG", 1, "2000-01-01"), rd("R", 5, "1999-01-01")]) == "PG"
    assert mod.pick_certification([rd("NC-17", 5, "2001-01-01")]) == "NC-17"


def test_pick_takes_earliest_within_type_and_ignores_blank():
    dates = [rd("", 3, "1980-01-01"), rd("PG", 3, "1990-01-01"), rd("G", 3, "1985-01-01")]
    assert mod.pick_certification(dates) == "G"
    assert mod.pick_certification([rd("", 3, "1980-01-01")]) is None
    assert mod.pick_certification([]) is None


def test_pick_ignores_non_mpaa_entries_even_when_earlier_or_higher_type():
    # 'NR' (not MPAA-mappable) must not beat a real MPAA mark on the same film,
    # even though it's an earlier date and a theatrical (type 3) release.
    assert mod.pick_certification([rd("NR", 3, "1980-01-01"), rd("R", 4, "1990-01-01")]) == "R"
    # 'TV-MA' must not beat a real MPAA mark even at the same/better type rank.
    assert mod.pick_certification([rd("TV-MA", 3, "1985-01-01"), rd("PG", 3, "1995-01-01")]) == "PG"
    # Only non-MPAA entries present -> None.
    assert mod.pick_certification([rd("NR", 3, "1990-01-01"), rd("TV-MA", 5, "1991-01-01")]) is None


def test_bucket_maps_mpaa_marks():
    assert [mod.bucket(c) for c in ["G", "PG", "PG-13", "R", "NC-17", "X"]] == \
        ["g", "pg", "pg13", "r", "nc17", "nc17"]
    assert mod.bucket("NR") is None
    assert mod.bucket("Unrated") is None
    assert mod.bucket(None) is None
    assert mod.bucket(" pg-13 ") == "pg13"


def test_build_parquet_keeps_rated_films_only(tmp_path):
    cache = tmp_path / "tmdb_release"
    cache.mkdir()
    (cache / "tt1.json").write_text(json.dumps({"tmdb_id": 1, "us": [rd("R", 3, "1990-01-01")]}))
    (cache / "tt2.json").write_text(json.dumps(None))
    (cache / "tt3.json").write_text(json.dumps({"tmdb_id": 3, "us": [rd("NR", 3, "1990-01-01")]}))
    (cache / "tt4.json").write_text(json.dumps({"tmdb_id": 4, "us": [rd("X", 3, "1972-01-01")]}))
    (cache / "tt5.json").write_text(json.dumps({"tmdb_id": 5, "us": []}))
    out = tmp_path / "ratings.parquet"
    assert mod.build_parquet(cache, out) == 2
    assert duckdb.sql(f"SELECT imdb_id, rating FROM '{out}' ORDER BY imdb_id").fetchall() == \
        [("tt1", "r"), ("tt4", "nc17")]
