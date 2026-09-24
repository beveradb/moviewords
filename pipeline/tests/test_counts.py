import json

import duckdb

from moviewords_pipeline.counts import build
from tests.fixtures.make_mini_corpus import build as build_zip

INDEX = [("tt0110912", "OpenSubtitles/raw/en/1994/110912/1.xml"),
         ("tt9999999", "OpenSubtitles/raw/en/2001/9999999/3.xml")]
RUNTIMES = {"tt0110912": 154, "tt9999999": 90}


def test_build_counts_and_stats(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    out_c, out_s = tmp_path / "wc.parquet", tmp_path / "ms.parquet"
    report = build(zip_path, INDEX, tmp_path / "cache", out_c, out_s, RUNTIMES)
    assert report == {"processed": 2, "skipped": 0, "failed": 0}
    wc = duckdb.sql(f"SELECT * FROM '{out_c}'").df()
    pulp = wc[wc.imdb_id == "tt0110912"]
    assert int(pulp[pulp.word == "cheese"]["count"].iloc[0]) == 400  # 2 lines x200
    ms = duckdb.sql(f"SELECT * FROM '{out_s}' ORDER BY imdb_id").df()
    assert list(ms.imdb_id) == ["tt0110912", "tt9999999"]
    assert ms.iloc[0].total_words == pulp["count"].sum()


def test_rerun_skips_cached_movies(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    build(zip_path, INDEX, *args, RUNTIMES)
    report = build(zip_path, INDEX, *args, RUNTIMES)
    assert report == {"processed": 0, "skipped": 2, "failed": 0}
    # compaction still produced full outputs from cache
    n = duckdb.sql(f"SELECT COUNT(DISTINCT imdb_id) FROM '{args[1]}'").fetchone()[0]
    assert n == 2


def test_changed_zip_name_invalidates_cache_entry(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    build(zip_path, INDEX, *args, RUNTIMES)
    new_index = [("tt0110912", "OpenSubtitles/raw/en/1994/110912/2.xml"), INDEX[1]]
    report = build(zip_path, new_index, *args, RUNTIMES)
    assert report == {"processed": 1, "skipped": 1, "failed": 0}


def test_unparseable_file_is_skipped_not_fatal_and_not_cached(tmp_path):
    import zipfile
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("OpenSubtitles/raw/en/1994/110912/1.xml", b"<broken")
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    report = build(zip_path, [INDEX[0]], *args, runtimes={})
    assert report == {"processed": 0, "skipped": 0, "failed": 1}
    assert not (tmp_path / "cache" / "tt0110912.json").exists()


def test_truncated_cache_file_is_treated_as_miss_and_repaired(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    out_c, out_s = tmp_path / "wc.parquet", tmp_path / "ms.parquet"
    # Simulate a process killed mid-write: truncated JSON.
    (cache_dir / "tt0110912.json").write_text('{"imdb_id": "tt0110912", "zip_')
    report = build(zip_path, INDEX, cache_dir, out_c, out_s, RUNTIMES)
    assert report == {"processed": 2, "skipped": 0, "failed": 0}
    record = json.loads((cache_dir / "tt0110912.json").read_text())
    assert record["imdb_id"] == "tt0110912"
    assert "counts" in record


def test_cache_file_missing_required_fields_is_treated_as_miss(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    out_c, out_s = tmp_path / "wc.parquet", tmp_path / "ms.parquet"
    # Valid JSON but missing the "counts" field that _compact() needs.
    (cache_dir / "tt0110912.json").write_text(json.dumps({
        "imdb_id": "tt0110912",
        "zip_name": INDEX[0][1],
    }))
    report = build(zip_path, INDEX, cache_dir, out_c, out_s, RUNTIMES)
    assert report == {"processed": 2, "skipped": 0, "failed": 0}
    record = json.loads((cache_dir / "tt0110912.json").read_text())
    assert "counts" in record


def test_workers_give_same_output_as_serial(tmp_path):
    zip_path = build_zip(tmp_path / "mini.zip")
    serial = (tmp_path / "c1", tmp_path / "wc1.parquet", tmp_path / "ms1.parquet")
    pooled = (tmp_path / "c2", tmp_path / "wc2.parquet", tmp_path / "ms2.parquet")
    build(zip_path, INDEX, *serial, RUNTIMES)
    report = build(zip_path, INDEX, *pooled, RUNTIMES, workers=4)
    assert report == {"processed": 2, "skipped": 0, "failed": 0}
    q = "SELECT * FROM '{}' ORDER BY ALL"
    assert duckdb.sql(q.format(serial[1])).fetchall() == duckdb.sql(q.format(pooled[1])).fetchall()
    assert duckdb.sql(q.format(serial[2])).fetchall() == duckdb.sql(q.format(pooled[2])).fetchall()


def test_fully_cached_run_never_opens_the_zip(tmp_path, monkeypatch):
    """Re-compacting from a warm cache must not touch the (possibly remote,
    34GB) zip."""
    from moviewords_pipeline import counts
    zip_path = build_zip(tmp_path / "mini.zip")
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    build(zip_path, INDEX, *args, RUNTIMES)

    def boom(*a, **k):
        raise AssertionError("zip opened on a fully cached run")
    monkeypatch.setattr(counts.opus_zip, "open_source", boom)
    report = build(tmp_path / "gone.zip", INDEX, *args, RUNTIMES)
    assert report == {"processed": 0, "skipped": 2, "failed": 0}


def test_fetch_error_counts_as_failed_not_fatal(tmp_path, monkeypatch):
    from moviewords_pipeline import counts

    class Flaky:
        def read(self, name):
            raise OSError("connection reset")
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            pass
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: Flaky())
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    report = build(tmp_path / "x.zip", INDEX, *args, RUNTIMES, workers=2)
    assert report == {"processed": 0, "skipped": 0, "failed": 2}
    assert not list((tmp_path / "cache").glob("*.json"))


def _doc(sentences):
    return ("<document>" + "".join(f'<s id="{i}">{t}</s>' for i, t in enumerate(sentences))
            + "</document>").encode()


GARBLED = "㐀㨀　㈀" * 40   # mis-encoded UTF-16: no English tokens
TOP, ALT1, ALT2 = (f"OpenSubtitles/raw/en/2006/383574/{n}.xml" for n in ("top", "a1", "a2"))


def _sparse_zip(tmp_path, top_sentences):
    import zipfile
    zip_path = tmp_path / "z.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, _doc(top_sentences))
        z.writestr(ALT1, _doc(["why is this happening I do not know"] * 300))
        z.writestr(ALT2, _doc(["why is this happening"] * 300))
    return zip_path


def test_sparse_top_pick_falls_back_to_wordiest_alternate(tmp_path):
    """Pirates of the Caribbean: Dead Man's Chest - the top-ranked file is half
    English, half mis-encoded garbage (378 bytes/word), so an alternate wins."""
    zip_path = _sparse_zip(tmp_path, ["Will!"] * 10 + [GARBLED] * 200)
    cache = tmp_path / "cache"
    args = (cache, tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    report = build(zip_path, [("tt0383574", TOP, [ALT2, ALT1])], *args, {"tt0383574": 151})
    assert report == {"processed": 1, "skipped": 0, "failed": 0}
    record = json.loads((cache / "tt0383574.json").read_text())
    assert record["zip_name"] == ALT1 and record["indexed_as"] == TOP
    assert record["total_words"] == 300 * 8
    # the verified result is a cache hit under the index's top pick
    report = build(zip_path, [("tt0383574", TOP, [ALT2, ALT1])], *args, {"tt0383574": 151})
    assert report == {"processed": 0, "skipped": 1, "failed": 0}


def test_dense_top_pick_never_fetches_alternates(tmp_path):
    zip_path = _sparse_zip(tmp_path, ["a perfectly normal line of film dialogue"] * 300)
    cache = tmp_path / "cache"
    build(zip_path, [("tt0383574", TOP, ["missing.xml"])], cache,
          tmp_path / "wc.parquet", tmp_path / "ms.parquet", {})
    record = json.loads((cache / "tt0383574.json").read_text())
    assert record["zip_name"] == TOP and "indexed_as" not in record


def test_sparse_top_pick_kept_when_alternates_are_no_better(tmp_path):
    """Musicals parse sparse in every file (lyrics are stripped) - keep the pick."""
    import zipfile
    zip_path = tmp_path / "z.zip"
    lyrics = ["♪ I dreamed a dream in time gone by ♪"] * 300
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, _doc(["At the end of the day"] * 20 + lyrics))
        z.writestr(ALT1, _doc(["At the end"] * 20 + lyrics))
    cache = tmp_path / "cache"
    build(zip_path, [("tt1707386", TOP, [ALT1])], cache,
          tmp_path / "wc.parquet", tmp_path / "ms.parquet", {})
    record = json.loads((cache / "tt1707386.json").read_text())
    assert record["zip_name"] == TOP and "indexed_as" not in record


def test_unparseable_top_pick_falls_back_to_alternate(tmp_path):
    import zipfile
    zip_path = tmp_path / "z.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, b"<broken")
        z.writestr(ALT1, _doc(["hello there"] * 50))
    cache = tmp_path / "cache"
    report = build(zip_path, [("tt0383574", TOP, [ALT1])], cache,
                   tmp_path / "wc.parquet", tmp_path / "ms.parquet", {})
    assert report == {"processed": 1, "skipped": 0, "failed": 0}
    assert json.loads((cache / "tt0383574.json").read_text())["zip_name"] == ALT1


def test_implausibly_fast_pick_with_half_size_alternate_is_a_double(tmp_path):
    """Dragon Seed: the pick counts 232 wpm and an alternate holds half its
    words - the pick is two subtitle tracks glued together."""
    import zipfile
    zip_path = tmp_path / "z.zip"
    line = "we must fight for the land our fathers gave us"   # 10 words
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, _doc([line] * 3000))    # 30,000 words in 100 min
        z.writestr(ALT1, _doc([line] * 2700))   # 90%: a real variant, not a half
        z.writestr(ALT2, _doc([line] * 1500))   # 50%: the single copy
    cache = tmp_path / "cache"
    build(zip_path, [("tt0036777", TOP, [ALT1, ALT2])], cache,
          tmp_path / "wc.parquet", tmp_path / "ms.parquet", {"tt0036777": 100})
    record = json.loads((cache / "tt0036777.json").read_text())
    assert record["zip_name"] == ALT2 and record["indexed_as"] == TOP
    assert record["total_words"] == 15_000


def test_fast_talker_without_half_size_twin_keeps_pick(tmp_path):
    import zipfile
    zip_path = tmp_path / "z.zip"
    line = "listen here you mug I got a story for the paper"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, _doc([line] * 2100))
        z.writestr(ALT1, _doc([line] * 1900))
    cache = tmp_path / "cache"
    build(zip_path, [("tt0032599", TOP, [ALT1])], cache,
          tmp_path / "wc.parquet", tmp_path / "ms.parquet", {"tt0032599": 92})
    assert json.loads((cache / "tt0032599.json").read_text())["zip_name"] == TOP
