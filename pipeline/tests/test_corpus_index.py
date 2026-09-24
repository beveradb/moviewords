from moviewords_pipeline.corpus_index import imdb_id_from_path, rank_candidates, select_best


def test_imdb_id_from_path():
    assert imdb_id_from_path("OpenSubtitles/raw/en/1994/110912/1.xml") == "tt0110912"
    assert imdb_id_from_path("OpenSubtitles/raw/en/2020/13320622/9.xml") == "tt13320622"
    assert imdb_id_from_path("OpenSubtitles/raw/en/1994/110912/") is None


def test_select_best_prefers_largest_in_band():
    # runtime 100 min -> plausible 500..40,000 words = 12.25KB..980KB of XML
    cands = [("a.xml", 5_000), ("b.xml", 200_000), ("c.xml", 240_000),
             ("d.xml", 5_000_000)]
    assert select_best(cands, 100) == "c.xml"


def test_select_best_takes_full_film_not_featurette():
    """The Wolf of Wall Street (180 min): ~30 full-length rips of 470-600KB
    plus one 44KB featurette. The old size/8 estimate put every full rip over
    its 250 words/min cap, so the featurette won (2,920 words, 12 'fucking')."""
    full = [(f"{i}.xml", size) for i, size in enumerate(
        [533_165, 542_952, 541_300, 578_238, 477_701, 603_898, 489_120])]
    cands = full + [("featurette.xml", 43_651)]
    assert select_best(cands, 180) == "5.xml"   # largest full rip


def test_select_best_keeps_talky_film_whose_every_rip_was_over_the_old_cap():
    """GoodFellas-style dialogue density: ~130 real words/min (the old cap
    rejected everything and the film vanished from the corpus)."""
    cands = [("a.xml", 460_000), ("b.xml", 470_000)]
    assert select_best(cands, 145) == "b.xml"


def test_select_best_takes_full_rip_when_forced_tracks_are_the_majority():
    """Spider-Man: No Way Home (148 min): 18 full rips of 297-374KB and ~50
    'forced' (foreign-dialogue-only) tracks of 1-24KB. A median-based guard
    lands on a forced track; peers + largest-first doesn't."""
    full = [(f"full{i}.xml", 297_000 + i * 4_000) for i in range(18)]
    forced = [(f"forced{i}.xml", 11_000 + i * 250) for i in range(50)]
    assert select_best(forced + full, 148) == "full17.xml"


def test_rank_candidates_puts_peerless_outliers_last():
    # 585KB and 442KB have no size peer within 1.25x; the ~316KB cluster does
    cands = [("double.xml", 585_000), ("odd.xml", 442_000),
             ("a.xml", 351_000), ("b.xml", 350_000), ("c.xml", 317_000),
             ("featurette.xml", 55_000)]
    assert rank_candidates(cands, 113) == [
        "a.xml", "b.xml", "c.xml", "double.xml", "odd.xml", "featurette.xml"]


def test_rank_candidates_two_unrelated_sizes_prefers_larger():
    assert rank_candidates([("small.xml", 60_000), ("big.xml", 300_000)], 100) == [
        "big.xml", "small.xml"]


def test_select_best_skips_doubled_file():
    # many ~315KB rips of the same film plus a merged/doubled 585KB file
    cands = [(f"{i}.xml", 315_000 + i * 100) for i in range(10)]
    cands.append(("double.xml", 585_000))
    assert select_best(cands, 113) == "9.xml"


def test_select_best_keeps_silent_film_captions():
    # ~6 words/min of intertitles: sparse but real
    assert select_best([("a.xml", 13_000)], 87) == "a.xml"


def test_select_best_none_when_all_outside_band():
    assert select_best([("a.xml", 10)], 100) is None


def test_select_best_uses_fallback_range_without_runtime():
    # no runtime -> 2,000..40,000 estimated words = 49KB..980KB
    assert select_best([("a.xml", 100_000), ("b.xml", 2_000_000)], None) == "a.xml"
    assert select_best([("a.xml", 10_000)], None) is None


def test_select_best_none_for_empty_candidates():
    assert select_best([], 100) is None


def test_load_blocklist_parses_ids_and_pairs(tmp_path, monkeypatch):
    from moviewords_pipeline import corpus_index
    bl = tmp_path / "mislabeled_subs.txt"
    bl.write_text(
        "# comment line\n"
        "\n"
        "tt0000001\n"
        "tt0149624 OpenSubtitles/raw/en/2000/149624/267165.xml LOTR sub\n"
    )
    monkeypatch.setattr(corpus_index, "BLOCKLIST_PATH", bl)
    ids, pairs = corpus_index.load_blocklist()
    assert ids == {"tt0000001"}
    assert pairs == {("tt0149624", "OpenSubtitles/raw/en/2000/149624/267165.xml")}


def test_blocklist_skips_file_and_film(tmp_path, monkeypatch):
    """A blocked zip_name falls through to the next-best candidate; a blocked
    imdb_id drops the film from the index entirely."""
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq
    import zipfile

    from moviewords_pipeline import config, corpus_index

    raw = tmp_path / "raw"; raw.mkdir()
    work = tmp_path / "work"; work.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "WORK_DIR", work)

    body = b'<?xml version="1.0" encoding="utf-8"?><document id="1">' \
           + b'<s id="1">hello there general kenobi today</s>' * 800 \
           + b"</document>"
    small = b'<?xml version="1.0" encoding="utf-8"?><document id="1">' \
            + b'<s id="1">hello there general kenobi today</s>' * 600 \
            + b"</document>"
    with zipfile.ZipFile(raw / "opus_en.zip", "w") as z:
        z.writestr("OpenSubtitles/raw/en/2000/1000001/9.xml", body)   # best
        z.writestr("OpenSubtitles/raw/en/2000/1000001/8.xml", small)  # runner-up
        z.writestr("OpenSubtitles/raw/en/2001/1000002/7.xml", body)

    pq.write_table(
        pa.table({"imdb_id": ["tt1000001", "tt1000002"],
                  "runtime_minutes": [90, 90]}),
        str(work / "curated.parquet"))

    bl = tmp_path / "bl.txt"
    bl.write_text("tt1000002\n"
                  "tt1000001 OpenSubtitles/raw/en/2000/1000001/9.xml\n")
    monkeypatch.setattr(corpus_index, "BLOCKLIST_PATH", bl)

    corpus_index.run()
    rows = duckdb.sql(
        f"SELECT imdb_id, zip_name, alternates FROM '{work / 'corpus_index.parquet'}'"
    ).fetchall()
    assert rows == [("tt1000001", "OpenSubtitles/raw/en/2000/1000001/8.xml", [])]


def test_index_records_ranked_alternates(tmp_path, monkeypatch):
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq
    import zipfile

    from moviewords_pipeline import config, corpus_index

    raw = tmp_path / "raw"; raw.mkdir()
    work = tmp_path / "work"; work.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "WORK_DIR", work)
    monkeypatch.setattr(config, "MAX_ALTERNATES", 2)
    monkeypatch.setattr(corpus_index, "BLOCKLIST_PATH", tmp_path / "none.txt")
    line = b'<s id="1">hello there general kenobi today</s>'
    with zipfile.ZipFile(raw / "opus_en.zip", "w") as z:
        for name, reps in (("1", 800), ("2", 790), ("3", 780), ("4", 770)):
            z.writestr(f"OpenSubtitles/raw/en/2000/1000001/{name}.xml",
                       b"<document>" + line * reps + b"</document>")
    pq.write_table(pa.table({"imdb_id": ["tt1000001"], "runtime_minutes": [90]}),
                   str(work / "curated.parquet"))
    corpus_index.run()
    (row,) = duckdb.sql(
        f"SELECT zip_name, alternates FROM '{work / 'corpus_index.parquet'}'"
    ).fetchall()
    prefix = "OpenSubtitles/raw/en/2000/1000001/"
    assert row == (prefix + "1.xml", [prefix + "2.xml", prefix + "3.xml"])
