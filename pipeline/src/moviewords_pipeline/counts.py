import json
import os
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from . import config, consensus, opus_zip
from .subtitle_parser import extract_text
from .wordcount import count_words

COUNTS_SCHEMA = pa.schema([("imdb_id", pa.string()), ("word", pa.string()),
                           ("count", pa.int32())])
STATS_SCHEMA = pa.schema([("imdb_id", pa.string()), ("total_words", pa.int64()),
                          ("unique_words", pa.int32()),
                          ("words_per_minute", pa.float64())])

FETCH_ATTEMPTS = 3

_CACHE_RECORD_FIELDS = ("imdb_id", "zip_name", "counts", "total_words",
                        "unique_words", "words_per_minute", "version",
                        "fingerprints", "selection")


def _load(cache_dir, imdb_id):
    """The film's cache record if it is well-formed and from the current
    FINGERPRINT_VERSION (parser/tokenizer changes invalidate), else None."""
    dest = cache_dir / f"{imdb_id}.json"
    if not dest.exists():
        return None
    try:
        record = json.loads(dest.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    if any(field not in record for field in _CACHE_RECORD_FIELDS):
        return None
    if record["version"] != config.FINGERPRINT_VERSION:
        return None
    return record


def _write_cache(cache_dir, imdb_id, record):
    dest = cache_dir / f"{imdb_id}.json"
    tmp = cache_dir / f"{imdb_id}.json.tmp"
    tmp.write_text(json.dumps(record))
    os.replace(tmp, dest)


def _candidate_names(row):
    """Index row -> candidate zip names, best rank first. Rows are
    (imdb_id, zip_name[, candidates]); without a candidate list the film's
    only candidate is zip_name."""
    imdb_id, zip_name, *rest = row
    cands = rest[0] if rest and rest[0] else [{"name": zip_name}]
    return [c["name"] if isinstance(c, dict) else c for c in cands]


def in_shard(imdb_id, shard):
    """Whether a film belongs to shard (k, n) - a stable split by id."""
    k, n = shard
    return zlib.crc32(imdb_id.encode()) % n == k


def build(zip_path, index_rows, cache_dir, out_counts, out_stats, runtimes,
          workers=1, out_selection=None, shard=None):
    """Choose and count every indexed film, reusing per-film caches.

    Each film's sampled candidates are fingerprinted (cached per file) and
    consensus.choose picks one; only the chosen file's full counts are kept.
    A record whose candidate list and selection rule are unchanged is reused
    without opening the zip; otherwise only files not yet fingerprinted are
    fetched (plus a newly chosen file whose full counts weren't kept). `workers` parallelises
    films (worth it against the remote zip, where each read is a network
    round trip). `out_selection`, if given, gets one row per film saying
    what was chosen and why (for review). With `shard` (k, n) only that
    shard's films are counted, into the cache only - run n shards as
    separate processes (parsing is GIL-bound), then once unsharded to write
    the outputs from the warm cache."""
    if shard:
        index_rows = [row for row in index_rows if in_shard(row[0], shard)]
    cache_dir.mkdir(parents=True, exist_ok=True)
    records, todo = {}, []
    for row in index_rows:
        imdb_id, names = row[0], _candidate_names(row)
        record = _load(cache_dir, imdb_id)
        # runtime feeds the doubled-file guard and words_per_minute, so a
        # corrected runtime (a later curate) re-chooses too
        if (record and record["selection"].get("candidates") == names
                and record.get("selection_version") == config.SELECTION_VERSION
                and record["selection"].get("runtime_minutes") == runtimes.get(imdb_id)):
            records[imdb_id] = record
        else:
            todo.append((imdb_id, names, record))
    skipped, processed, failed = len(records), 0, 0
    if todo:
        with opus_zip.open_source(zip_path) as z:
            def fetch(zip_name):
                """Raw bytes, retrying transient errors; None if unreadable."""
                for attempt in range(FETCH_ATTEMPTS):
                    try:
                        return z.read(zip_name)
                    except (OSError, requests.RequestException, zipfile.BadZipFile,
                            zlib.error, KeyError, NotImplementedError) as exc:
                        if attempt == FETCH_ATTEMPTS - 1:
                            print(f"count {zip_name}: {exc!r}")
                return None

            def count_one(item):
                imdb_id, names, old = item
                runtime = runtimes.get(imdb_id)
                known = old["fingerprints"] if old else {}
                fps, full = {}, {}
                for name in names:
                    if name in known:
                        fps[name] = known[name]
                        continue
                    raw = fetch(name)
                    if raw is None:
                        # a fetch failure is not evidence against the file:
                        # fail the film (uncached, retried next run) rather
                        # than choose without it
                        return None
                    full[name] = count_words(extract_text(raw))
                    fps[name] = consensus.fingerprint(full[name], len(raw))
                chosen, info = consensus.choose([(n, fps[n]) for n in names], runtime)
                if chosen is None:
                    return None
                if chosen in full:
                    counts = full[chosen]
                elif old and old["zip_name"] == chosen:
                    counts = old["counts"]
                else:
                    raw = fetch(chosen)
                    if raw is None:
                        return None
                    counts = count_words(extract_text(raw))
                total = sum(counts.values())
                record = {"imdb_id": imdb_id, "zip_name": chosen, "counts": counts,
                          "total_words": total, "unique_words": len(counts),
                          "words_per_minute": total / runtime if runtime else None,
                          "version": config.FINGERPRINT_VERSION,
                          "selection_version": config.SELECTION_VERSION,
                          "fingerprints": fps,
                          "selection": info | {"rank_top": names[0], "candidates": names,
                                               "runtime_minutes": runtime}}
                _write_cache(cache_dir, imdb_id, record)
                return record

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for i, record in enumerate(pool.map(count_one, todo), 1):
                    if record:
                        records[record["imdb_id"]] = record
                        processed += 1
                    else:
                        failed += 1
                    if i % 1000 == 0:
                        print(f"count stage: {i}/{len(todo)} uncached entries")
    if shard:
        return {"processed": processed, "skipped": skipped, "failed": failed}
    ordered = [records[row[0]] for row in index_rows if row[0] in records]
    _compact(ordered, out_counts, out_stats)
    if out_selection:
        _write_selection(ordered, out_selection)
    return {"processed": processed, "skipped": skipped, "failed": failed}


def _compact(records, out_counts, out_stats):
    # One `write_table` call per movie == one row group per movie in the output
    # parquet file. derive.py's per-movie hot-path queries (`SELECT word, count
    # FROM wc WHERE imdb_id = ?`) rely on this layout for row-group pruning: DuckDB
    # can skip whole row groups whose min/max imdb_id doesn't match the filter
    # instead of scanning the entire file. If this ever gets rewritten to batch
    # multiple movies into a single write_table call, that pruning benefit is lost
    # and derive's per-movie queries get much slower on the full corpus.
    with pq.ParquetWriter(out_counts, COUNTS_SCHEMA) as writer:
        for r in records:
            words, nums = zip(*sorted(r["counts"].items())) if r["counts"] else ((), ())
            writer.write_table(pa.table(
                {"imdb_id": [r["imdb_id"]] * len(words), "word": list(words),
                 "count": list(nums)}, schema=COUNTS_SCHEMA))
    pq.write_table(pa.table(
        {"imdb_id": [r["imdb_id"] for r in records],
         "total_words": [r["total_words"] for r in records],
         "unique_words": [r["unique_words"] for r in records],
         "words_per_minute": [r["words_per_minute"] for r in records]},
        schema=STATS_SCHEMA), out_stats)


def _write_selection(records, out):
    sel = [r["selection"] for r in records]
    pq.write_table(pa.table({
        "imdb_id": [r["imdb_id"] for r in records],
        "zip_name": [r["zip_name"] for r in records],
        "rank_top": [s["rank_top"] for s in sel],
        "reason": [s["reason"] for s in sel],
        "candidates": pa.array([len(s["candidates"]) for s in sel], pa.int32()),
        "usable": pa.array([s["usable"] for s in sel], pa.int32()),
        "cluster": pa.array([s["cluster"] for s in sel], pa.int32()),
        "relaxed": [s["relaxed"] for s in sel],
        "rejected": [json.dumps(s["rejected"]) for s in sel],
    }), out)


def run(workers=1, shard=None):
    index_rows = duckdb.sql(
        f"SELECT imdb_id, zip_name, candidates "
        f"FROM '{config.WORK_DIR / 'corpus_index.parquet'}'"
    ).fetchall()
    runtimes = dict(duckdb.sql(
        f"SELECT imdb_id, runtime_minutes FROM '{config.WORK_DIR / 'curated.parquet'}'"
    ).fetchall())
    report = build(config.RAW_DIR / "opus_en.zip", index_rows,
                   config.WORK_DIR / "counts" / config.LANG,
                   config.WORK_DIR / "word_counts.parquet",
                   config.WORK_DIR / "movie_stats.parquet", runtimes,
                   workers=workers,
                   out_selection=config.WORK_DIR / "selection.parquet",
                   shard=shard)
    print(f"count stage: {report}")
