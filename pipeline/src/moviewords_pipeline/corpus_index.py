import re
from collections import defaultdict
from pathlib import Path

import duckdb
import pyarrow as pa

from . import config, opus_zip

PATH_RE = re.compile(r"OpenSubtitles/raw/en/\d{4}/(\d+)/\d+\.xml$")

BLOCKLIST_PATH = Path(__file__).with_name("mislabeled_subs.txt")


def load_blocklist():
    """(blocked imdb_ids, blocked (imdb_id, zip_name) pairs) from the
    mislabeled-subtitles data file. Lines: imdb_id [zip_name] [comment]."""
    ids, pairs = set(), set()
    if not BLOCKLIST_PATH.exists():
        return ids, pairs
    for line in BLOCKLIST_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 1:
            ids.add(parts[0])
        else:
            pairs.add((parts[0], parts[1]))
    return ids, pairs


def imdb_id_from_path(name):
    m = PATH_RE.search(name)
    if not m:
        return None
    return "tt" + m.group(1).zfill(7)


def rank_candidates(candidates, runtime_minutes):
    """Order a film's (zip_name, size_bytes) subtitle candidates best-first.

    Only files in the plausible words-per-minute band qualify, and (given
    enough candidates) none over MAX_SIZE_VS_UPPER_QUARTILE x the upper
    quartile size. Among those,
    files with a size PEER (another candidate within MAX_PEER_SIZE_RATIO)
    come first, largest first, then peerless ones, largest first. Real
    full-length rips cluster in size across a film's many uploads, while the
    usual bad picks don't: a doubled/merged file is a lone outlier above the
    cluster, and a lone featurette or partial sits below it. (Forced-only
    tracks do cluster, but below the full rips, so largest-first still wins.)
    [] if nothing is in band."""
    if runtime_minutes:
        lo = runtime_minutes * config.MIN_WORDS_PER_MIN
        hi = runtime_minutes * config.MAX_WORDS_PER_MIN
    else:
        lo, hi = config.FALLBACK_WORD_RANGE
    in_band = sorted(((size, name) for name, size in candidates
                      if lo <= size / config.BYTES_PER_WORD <= hi), reverse=True)
    if len(in_band) >= config.MIN_CANDIDATES_FOR_CAP:
        # doubled files can come in pairs (Forrest Gump: two ~450KB doubles
        # peer each other above a ~25-file ~250KB cluster), so also cap
        # against the upper quartile - robust while forced tracks and other
        # small files are under 3/4 of the directory
        ascending = sorted(size for size, _ in in_band)
        upper_quartile = ascending[int(0.75 * (len(ascending) - 1))]
        in_band = [(size, name) for size, name in in_band
                   if size <= upper_quartile * config.MAX_SIZE_VS_UPPER_QUARTILE]
    if len(in_band) <= 1:
        return [name for _, name in in_band]
    sizes = [size for size, _ in in_band]
    ratio = config.MAX_PEER_SIZE_RATIO

    def has_peer(k):   # sorted, so the nearest peer is an adjacent entry
        return ((k > 0 and sizes[k - 1] <= sizes[k] * ratio)
                or (k + 1 < len(sizes) and sizes[k + 1] * ratio >= sizes[k]))
    peered = [name for k, (_, name) in enumerate(in_band) if has_peer(k)]
    peerless = [name for k, (_, name) in enumerate(in_band) if not has_peer(k)]
    return peered + peerless


def sample_candidates(ranked, k):
    """Up to k of a ranked list, spread evenly from first to last (the rank-
    top always included) - an unbiased sample for the count stage's content
    consensus, not just the largest files."""
    n = len(ranked)
    if n <= k:
        return list(ranked)
    if k == 1:
        return ranked[:1]
    return [ranked[round(i * (n - 1) / (k - 1))] for i in range(k)]


def select_best(candidates, runtime_minutes):
    """The top-ranked candidate (see rank_candidates), or None."""
    ranked = rank_candidates(candidates, runtime_minutes)
    return ranked[0] if ranked else None


def run():
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    curated = duckdb.sql(
        f"SELECT imdb_id, runtime_minutes FROM '{config.WORK_DIR / 'curated.parquet'}'"
    ).fetchall()
    runtimes = dict(curated)
    blocked_ids, blocked_files = load_blocklist()
    by_movie = defaultdict(list)
    with opus_zip.open_source() as z:
        for info in z.infolist():
            imdb_id = imdb_id_from_path(info.filename)
            if imdb_id in blocked_ids:
                continue
            if imdb_id in runtimes:
                if (imdb_id, info.filename) in blocked_files:
                    continue
                by_movie[imdb_id].append((info.filename, info.file_size))
    rows = []
    for imdb_id, cands in by_movie.items():
        ranked = rank_candidates(cands, runtimes[imdb_id])
        if ranked:
            size = dict(cands)
            sample = sample_candidates(ranked, config.CONSENSUS_MAX_CANDIDATES)
            rows.append((imdb_id, ranked[0],
                         [{"name": n, "bytes": size[n]} for n in sample]))
    # `zip_name` is the size ranking's pick; the count stage chooses among
    # `candidates` by content (see consensus.py) and records the file used
    table = pa.table({
        "imdb_id": pa.array([r[0] for r in rows], type=pa.string()),
        "zip_name": pa.array([r[1] for r in rows], type=pa.string()),
        "candidates": pa.array([r[2] for r in rows], type=pa.list_(pa.struct(
            [("name", pa.string()), ("bytes", pa.int64())]))),
    })
    import pyarrow.parquet as pq
    pq.write_table(table, str(config.WORK_DIR / "corpus_index.parquet"))
