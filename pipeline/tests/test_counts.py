import json

import duckdb
import pytest

from moviewords_pipeline.counts import build
from tests.fixtures.make_mini_corpus import build as build_zip

INDEX = [("tt0110912", "OpenSubtitles/raw/en/1994/110912/1.xml"),
         ("tt9999999", "OpenSubtitles/raw/en/2001/9999999/3.xml")]
RUNTIMES = {"tt0110912": 154, "tt9999999": 90}


@pytest.fixture(autouse=True)
def _no_style_model(monkeypatch):
    """These fixtures repeat one sentence hundreds of times, which the
    machine-translation style model rightly finds unnatural; the model has
    its own tests (test_quality)."""
    from moviewords_pipeline import config
    monkeypatch.setattr(config, "MT_SCORE_MAX", 1.01)


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


def _row(imdb_id, *names):
    return (imdb_id, names[0], [{"name": n, "bytes": 0} for n in names])


def _zip(tmp_path, files):
    import zipfile
    zip_path = tmp_path / "z.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for name, sentences in files.items():
            z.writestr(name, _doc(sentences))
    return zip_path


def _record(tmp_path, imdb_id):
    return json.loads((tmp_path / "cache" / f"{imdb_id}.json").read_text())


def _build(tmp_path, zip_path, rows, runtimes=None, **kw):
    return build(zip_path, rows, tmp_path / "cache", tmp_path / "wc.parquet",
                 tmp_path / "ms.parquet", runtimes or {}, **kw)


class _CountingZip:
    """Wraps a real zip, recording every member read."""
    def __init__(self, zip_path, reads, fail=()):
        import zipfile
        self.z, self.reads, self.fail = zipfile.ZipFile(zip_path), reads, fail

    def read(self, name):
        self.reads.append(name)
        if name in self.fail:
            raise OSError("read timed out")
        return self.z.read(name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


REAL = "I know that honest iago is with cassio and the moor in venice."
WRONG = "You know that odin is with hugo and the coach in the gym."


def test_majority_beats_a_larger_mislabeled_file(tmp_path):
    """Othello 1951: the O (2001) upload is the biggest file (the size
    ranking's pick), but the other uploads agree with each other."""
    zip_path = _zip(tmp_path, {TOP: [WRONG] * 400, ALT1: [REAL] * 300, ALT2: [REAL] * 310})
    report = _build(tmp_path, zip_path, [_row("tt0045251", TOP, ALT1, ALT2)])
    assert report == {"processed": 1, "skipped": 0, "failed": 0}
    record = _record(tmp_path, "tt0045251")
    assert record["zip_name"] in (ALT1, ALT2)
    assert record["selection"]["reason"] == "consensus"
    assert record["selection"]["rank_top"] == TOP
    assert set(record["fingerprints"]) == {TOP, ALT1, ALT2}
    # every fingerprint carries the quality features selection rules use
    q = record["fingerprints"][ALT1]["q"]
    assert {"toks_per_line", "cap_start", "mt", "style"} <= set(q)


def test_sparse_garbage_pick_loses_to_readable_candidates(tmp_path):
    """Pirates: Dead Man's Chest - the rank-top is half mis-encoded garbage."""
    zip_path = _zip(tmp_path, {TOP: ["Will!"] * 10 + [GARBLED] * 200,
                               ALT1: [REAL] * 300, ALT2: [REAL] * 300})
    _build(tmp_path, zip_path, [_row("tt0383574", TOP, ALT1, ALT2)])
    record = _record(tmp_path, "tt0383574")
    assert record["zip_name"] == ALT1
    assert record["selection"]["rejected"] == {TOP: "tiny"}


def test_musical_keeps_a_file_when_every_candidate_is_sparse(tmp_path):
    """Lyrics are stripped, so every file of a musical parses sparse."""
    lyrics = ["♪ I dreamed a dream in time gone by ♪"] * 300
    zip_path = _zip(tmp_path, {TOP: ["At the end of the day it is another day"] * 30 + lyrics,
                               ALT1: ["At the end of the day it is another day"] * 28 + lyrics})
    _build(tmp_path, zip_path, [_row("tt1707386", TOP, ALT1)])
    record = _record(tmp_path, "tt1707386")
    assert record["zip_name"] == TOP and record["selection"]["relaxed"] is True


def test_unparseable_rank_top_falls_back_to_a_readable_file(tmp_path):
    import zipfile
    zip_path = tmp_path / "z.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(TOP, b"<broken")
        z.writestr(ALT1, _doc([REAL] * 50))
    report = _build(tmp_path, zip_path, [_row("tt0383574", TOP, ALT1)])
    assert report == {"processed": 1, "skipped": 0, "failed": 0}
    assert _record(tmp_path, "tt0383574")["zip_name"] == ALT1


def test_doubled_file_loses_to_the_single_copy(tmp_path):
    """Dragon Seed: two subtitle tracks glued together (232 wpm)."""
    line = "we must fight for the land our fathers gave us"   # 10 words
    zip_path = _zip(tmp_path, {TOP: [line] * 3000, ALT1: [line] * 2700, ALT2: [line] * 1500})
    _build(tmp_path, zip_path, [_row("tt0036777", TOP, ALT1, ALT2)], {"tt0036777": 100})
    record = _record(tmp_path, "tt0036777")
    assert record["zip_name"] == ALT2 and record["total_words"] == 15_000


def test_fast_talker_without_half_size_twin_keeps_pick(tmp_path):
    line = "listen here you mug I got a story for the paper"
    zip_path = _zip(tmp_path, {TOP: [line] * 2100, ALT1: [line] * 1900})
    _build(tmp_path, zip_path, [_row("tt0032599", TOP, ALT1)], {"tt0032599": 92})
    assert _record(tmp_path, "tt0032599")["zip_name"] == TOP


def test_fetch_failure_on_any_candidate_fails_the_film_uncached(tmp_path, monkeypatch):
    """A network blip is not evidence against a file: fail the film
    (retried next run) instead of caching a choice made without it."""
    from moviewords_pipeline import counts
    zip_path = _zip(tmp_path, {TOP: [REAL] * 300, ALT1: [REAL] * 300})
    monkeypatch.setattr(counts.opus_zip, "open_source",
                        lambda p: _CountingZip(zip_path, [], fail={ALT1}))
    report = _build(tmp_path, zip_path, [_row("tt0383574", TOP, ALT1)])
    assert report == {"processed": 0, "skipped": 0, "failed": 1}
    assert not (tmp_path / "cache" / "tt0383574.json").exists()


def test_transient_fetch_error_is_retried(tmp_path, monkeypatch):
    import zipfile
    import zlib
    from moviewords_pipeline import counts
    zip_path = build_zip(tmp_path / "mini.zip")
    calls = []

    class FlakyOnce:
        def __init__(self):
            self.z = zipfile.ZipFile(zip_path)
        def read(self, name):
            calls.append(name)
            if len(calls) == 1:
                raise zlib.error("incomplete stream")
            return self.z.read(name)
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            pass
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: FlakyOnce())
    report = build(zip_path, [INDEX[0]], tmp_path / "cache",
                   tmp_path / "wc.parquet", tmp_path / "ms.parquet", RUNTIMES)
    assert report == {"processed": 1, "skipped": 0, "failed": 0}


def test_new_candidate_only_fetches_the_new_file(tmp_path, monkeypatch):
    from moviewords_pipeline import counts
    zip_path = _zip(tmp_path, {TOP: [REAL] * 300, ALT1: [REAL] * 300, ALT2: [REAL] * 305})
    _build(tmp_path, zip_path, [_row("tt0045251", TOP, ALT1)])
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    report = _build(tmp_path, zip_path, [_row("tt0045251", TOP, ALT1, ALT2)])
    assert report == {"processed": 1, "skipped": 0, "failed": 0}
    assert reads == [ALT2]


def test_chosen_file_known_only_by_fingerprint_is_refetched_for_counts(tmp_path, monkeypatch):
    """Dropping a candidate can make a previously unchosen file win: its full
    counts were never stored, so it is read again."""
    from moviewords_pipeline import counts
    zip_path = _zip(tmp_path, {TOP: [WRONG] * 400, ALT1: [REAL] * 300, ALT2: [REAL] * 310})
    _build(tmp_path, zip_path, [_row("tt0045251", TOP, ALT1, ALT2)])
    first = _record(tmp_path, "tt0045251")["zip_name"]
    remaining = ALT2 if first == ALT1 else ALT1
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    _build(tmp_path, zip_path, [_row("tt0045251", remaining, TOP)])
    record = _record(tmp_path, "tt0045251")
    assert record["zip_name"] == remaining and reads == [remaining]
    assert record["total_words"] == sum(record["counts"].values()) > 0


def test_fingerprint_version_bump_refetches_everything(tmp_path, monkeypatch):
    from moviewords_pipeline import config, counts
    zip_path = _zip(tmp_path, {TOP: [REAL] * 300, ALT1: [REAL] * 300})
    rows = [_row("tt0045251", TOP, ALT1)]
    _build(tmp_path, zip_path, rows)
    assert _build(tmp_path, zip_path, rows)["skipped"] == 1
    monkeypatch.setattr(config, "FINGERPRINT_VERSION", config.FINGERPRINT_VERSION + 1)
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    assert _build(tmp_path, zip_path, rows)["processed"] == 1
    assert sorted(reads) == sorted([TOP, ALT1])


def test_selection_version_bump_rechooses_from_cached_fingerprints(tmp_path, monkeypatch):
    """A new selection rule re-runs choose() on the stored fingerprints; only
    a newly chosen file whose full counts were never kept is read."""
    from moviewords_pipeline import config, consensus, counts
    zip_path = _zip(tmp_path, {TOP: [REAL] * 300, ALT1: [REAL] * 310})
    rows = [_row("tt0045251", TOP, ALT1)]
    _build(tmp_path, zip_path, rows)
    first = _record(tmp_path, "tt0045251")["zip_name"]
    other = ALT1 if first == TOP else TOP
    monkeypatch.setattr(config, "SELECTION_VERSION", config.SELECTION_VERSION + 1)
    monkeypatch.setattr(consensus, "choose", lambda cands, rt, cast=None: (other, {"reason": "rank",
                        "cluster": 1, "usable": 2, "relaxed": False, "rejected": {}}))
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    assert _build(tmp_path, zip_path, rows)["processed"] == 1
    assert reads == [other]
    record = _record(tmp_path, "tt0045251")
    assert record["zip_name"] == other and record["selection_version"] == config.SELECTION_VERSION
    # and a rerun under the same rule is a pure cache hit
    assert _build(tmp_path, zip_path, rows)["skipped"] == 1


def test_selection_report_says_what_was_chosen_and_why(tmp_path):
    zip_path = _zip(tmp_path, {TOP: [WRONG] * 400, ALT1: [REAL] * 300, ALT2: [REAL] * 310})
    out = tmp_path / "selection.parquet"
    _build(tmp_path, zip_path, [_row("tt0045251", TOP, ALT1, ALT2)], out_selection=out)
    (row,) = duckdb.sql(f"SELECT imdb_id, rank_top, reason, candidates, usable, cluster, "
                        f"relaxed, rejected FROM '{out}'").fetchall()
    assert row == ("tt0045251", TOP, "consensus", 3, 3, 2, False, "{}")


def test_shards_partition_the_films_and_only_fill_the_cache(tmp_path):
    """count --shard i/n: n processes each fill the cache for their films
    (no parquet outputs); an unsharded run then compacts from cache alone."""
    from moviewords_pipeline.counts import in_shard
    ids = [f"tt{i:07d}" for i in range(200)]
    shards = [[i for i in ids if in_shard(i, (k, 4))] for k in range(4)]
    assert sorted(sum(shards, [])) == ids and all(shards)
    zip_path = build_zip(tmp_path / "mini.zip")
    args = (tmp_path / "cache", tmp_path / "wc.parquet", tmp_path / "ms.parquet")
    for k in range(3):
        build(zip_path, INDEX, *args, RUNTIMES, shard=(k, 3))
    assert not args[1].exists()
    assert build(zip_path, INDEX, *args, RUNTIMES) == {"processed": 0, "skipped": 2, "failed": 0}
    assert args[1].exists()


def test_changed_runtime_rechooses_without_refetching(tmp_path, monkeypatch):
    """runtime drives the doubled-file guard and words_per_minute: a corrected
    runtime from a later curate must re-choose (from cached fingerprints)."""
    from moviewords_pipeline import counts
    line = "we must fight for the land our fathers gave us"
    zip_path = _zip(tmp_path, {TOP: [line] * 3000, ALT1: [line] * 1500})
    rows = [_row("tt0036777", TOP, ALT1)]
    _build(tmp_path, zip_path, rows, {})                       # runtime unknown
    assert _record(tmp_path, "tt0036777")["zip_name"] == TOP
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    assert _build(tmp_path, zip_path, rows, {"tt0036777": 100})["processed"] == 1
    record = _record(tmp_path, "tt0036777")
    assert record["zip_name"] == ALT1 and record["words_per_minute"] == 150
    assert reads == [ALT1]          # only the newly chosen file's full counts
    assert _build(tmp_path, zip_path, rows, {"tt0036777": 100})["skipped"] == 1


VIET = "toi khong biet ong co the lam gi"


def test_film_with_only_other_language_files_is_dropped_and_cached(tmp_path, monkeypatch):
    """Every file fails a hard gate: the film is left out of the counts, and
    the decision is cached so the next run doesn't read the files again."""
    zip_path = _zip(tmp_path, {TOP: [VIET] * 300, ALT1: [REAL] * 300})
    rows = [_row("tt0000001", TOP), ("tt0000002", ALT1, [{"name": ALT1, "bytes": 0}])]
    out = tmp_path / "sel.parquet"
    assert _build(tmp_path, zip_path, rows, out_selection=out) == {
        "processed": 2, "skipped": 0, "failed": 0}
    counted = {r[0] for r in duckdb.sql(f"SELECT DISTINCT imdb_id FROM '{tmp_path / 'wc.parquet'}'").fetchall()}
    assert counted == {"tt0000002"}
    sel = dict(duckdb.sql(f"SELECT imdb_id, tier FROM '{out}'").fetchall())
    assert sel == {"tt0000001": "drop", "tt0000002": "ok"}
    from moviewords_pipeline import counts
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    assert _build(tmp_path, zip_path, rows)["skipped"] == 2 and reads == []


def test_new_cast_list_rechooses_from_cached_fingerprints(tmp_path, monkeypatch):
    """TMDB credits fetched after a count: the wrong-film check must run, and
    needs no reads beyond a newly chosen file."""
    from moviewords_pipeline import counts
    zip_path = _zip(tmp_path, {TOP: [WRONG] * 400, ALT1: [REAL] * 300})
    rows = [_row("tt0045251", TOP, ALT1)]
    _build(tmp_path, zip_path, rows)
    assert _record(tmp_path, "tt0045251")["zip_name"] == TOP     # size rank, no agreement
    cast = {"tt0045251": {"strict": frozenset({"cassio", "iago"}),
                          "broad": frozenset({"cassio", "iago", "moor"})}}
    reads = []
    monkeypatch.setattr(counts.opus_zip, "open_source", lambda p: _CountingZip(zip_path, reads))
    assert _build(tmp_path, zip_path, rows, casts=cast)["processed"] == 1
    record = _record(tmp_path, "tt0045251")
    assert record["zip_name"] == ALT1 and reads == [ALT1]
    assert record["selection"]["flagged"] == {TOP: ["wrong-cast"]}
