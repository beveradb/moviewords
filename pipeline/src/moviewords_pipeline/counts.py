import json
import os
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from . import config, opus_zip
from .subtitle_parser import extract_text
from .wordcount import count_words

COUNTS_SCHEMA = pa.schema([("imdb_id", pa.string()), ("word", pa.string()),
                           ("count", pa.int32())])
STATS_SCHEMA = pa.schema([("imdb_id", pa.string()), ("total_words", pa.int64()),
                          ("unique_words", pa.int32()),
                          ("words_per_minute", pa.float64())])

FETCH_ATTEMPTS = 3

_CACHE_RECORD_FIELDS = ("imdb_id", "zip_name", "counts", "total_words",
                        "unique_words", "words_per_minute")


def _cached(cache_dir, imdb_id, zip_name, alternates=()):
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
    if record.get("zip_name") == zip_name:
        return record
    # `indexed_as`: the top pick was verified but an alternate won - still
    # valid only while that alternate is a current (non-blocklisted) one
    if record.get("indexed_as") == zip_name and record.get("zip_name") in alternates:
        return record
    return None


def _write_cache(cache_dir, imdb_id, record):
    dest = cache_dir / f"{imdb_id}.json"
    tmp = cache_dir / f"{imdb_id}.json.tmp"
    tmp.write_text(json.dumps(record))
    os.replace(tmp, dest)


def build(zip_path, index_rows, cache_dir, out_counts, out_stats, runtimes,
          workers=1):
    """Count every indexed film, reusing per-film caches. The zip is only
    opened when something is uncached; `workers` parallelises the fetch+parse
    of uncached entries (worth it against the remote zip, where each read is
    a network round trip)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    records, todo = {}, []
    for imdb_id, zip_name, *rest in index_rows:
        record = _cached(cache_dir, imdb_id, zip_name, rest[0] if rest else ())
        if record:
            records[imdb_id] = record
        else:
            todo.append((imdb_id, zip_name, rest[0] if rest else ()))
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

            def parse(raw):
                """(counts, raw byte size), or None if no words parse out."""
                counts = count_words(extract_text(raw))
                return (counts, len(raw)) if counts else None

            def parse_alt(zip_name):
                raw = fetch(zip_name)
                return parse(raw) if raw is not None else None

            def count_one(row):
                imdb_id, zip_name, alternates = row
                runtime = runtimes.get(imdb_id)
                raw = fetch(zip_name)
                if raw is None:
                    # a fetch failure is not evidence against the file: fail
                    # (uncached, retried next run) rather than cache a fallback
                    return None
                best, chosen = parse(raw), zip_name
                if (best is None
                        or best[1] / sum(best[0].values()) > config.MAX_BYTES_PER_WORD):
                    # unreadable or suspiciously sparse: keep whichever
                    # candidate says the most
                    for alt in alternates:
                        parsed = parse_alt(alt)
                        if parsed and (best is None or sum(parsed[0].values())
                                       > sum(best[0].values())):
                            best, chosen = parsed, alt
                elif runtime and sum(best[0].values()) / runtime > config.MAX_COUNTED_WPM:
                    # implausibly fast: if an alternate holds about half the
                    # words, the pick is a doubled file - take the half
                    top_total = sum(best[0].values())
                    for alt in alternates:
                        parsed = parse_alt(alt)
                        if parsed and 0.4 <= sum(parsed[0].values()) / top_total <= 0.6:
                            best, chosen = parsed, alt
                            break
                if best is None:
                    return None
                counts = best[0]
                total = sum(counts.values())
                record = {"imdb_id": imdb_id, "zip_name": chosen, "counts": counts,
                          "total_words": total, "unique_words": len(counts),
                          "words_per_minute": total / runtime if runtime else None}
                if chosen != zip_name:
                    record["indexed_as"] = zip_name
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
    ordered = [records[row[0]] for row in index_rows if row[0] in records]
    _compact(ordered, out_counts, out_stats)
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


def run(workers=1):
    index_rows = duckdb.sql(
        f"SELECT imdb_id, zip_name, alternates "
        f"FROM '{config.WORK_DIR / 'corpus_index.parquet'}'"
    ).fetchall()
    runtimes = dict(duckdb.sql(
        f"SELECT imdb_id, runtime_minutes FROM '{config.WORK_DIR / 'curated.parquet'}'"
    ).fetchall())
    report = build(config.RAW_DIR / "opus_en.zip", index_rows,
                   config.WORK_DIR / "counts" / config.LANG,
                   config.WORK_DIR / "word_counts.parquet",
                   config.WORK_DIR / "movie_stats.parquet", runtimes,
                   workers=workers)
    print(f"count stage: {report}")
