"""TMDB cast lists, for checking that a subtitle names the right film's
characters (quality.cast_hits). One request per film: TMDB's /movie/{id}
accepts an IMDb id directly. Cached per film in work/tmdb_credits/, 'null'
for no match, like the tmdb stage."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import duckdb
import requests

from . import config
from .tmdb import BASE, make_session

MAX_CAST = 40
_local = threading.local()


def lookup(imdb_id, session):
    """{"imdb_id", "tmdb_id", "characters", "actors"} for the top-billed cast,
    or None if TMDB has no such film."""
    resp = session.get(f"{BASE}/movie/{imdb_id}",
                       params={"append_to_response": "credits"}, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    cast = (data.get("credits") or {}).get("cast") or []
    cast = [c for c in cast if isinstance(c, dict)][:MAX_CAST]
    return {"imdb_id": imdb_id, "tmdb_id": data.get("id"),
            "characters": [c.get("character") or "" for c in cast],
            "actors": [c.get("name") or "" for c in cast]}


def load(imdb_id, cache_dir=None):
    """The cached record, None for a cached no-match, or KeyError if never
    fetched."""
    path = (cache_dir or config.WORK_DIR / "tmdb_credits") / f"{imdb_id}.json"
    if not path.exists():
        raise KeyError(imdb_id)
    return json.loads(path.read_text())


def run(workers=6):
    cache = config.WORK_DIR / "tmdb_credits"
    cache.mkdir(parents=True, exist_ok=True)
    ids = [r[0] for r in duckdb.sql(
        f"SELECT imdb_id FROM '{config.WORK_DIR / 'corpus_index.parquet'}'").fetchall()]
    todo = [i for i in ids if not (cache / f"{i}.json").exists()]
    make_session()   # fail fast without credentials

    def fetch(imdb_id):
        if not hasattr(_local, "session"):
            _local.session = make_session()
        time.sleep(0.15)   # ~6 workers x ~6/s, under TMDB's ~50/s limit
        try:
            record = lookup(imdb_id, _local.session)
        except (requests.RequestException, ValueError, AttributeError, TypeError) as exc:
            print(f"credits {imdb_id}: {exc}")
            return False
        tmp = cache / f"{imdb_id}.json.tmp"
        tmp.write_text(json.dumps(record))
        os.replace(tmp, cache / f"{imdb_id}.json")
        return True

    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, ok in enumerate(pool.map(fetch, todo), 1):
            done += ok
            failed += not ok
            if i % 5000 == 0:
                print(f"credits stage: {i}/{len(todo)}")
    print(f"credits stage: fetched={done} failed={failed} total={len(ids)}")
