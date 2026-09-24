# MPAA Rating Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Trends-page rating filter (`All ratings | G | PG | PG-13 | R | NC-17/X`, URL `rating=`) backed by TMDB US certifications and per-rating trend bakes.

**Architecture:** `fetch_ratings.py` caches each film's TMDB US release dates and writes `ratings.parquet`. Per-rating input slices (movies, words, word_year re-derived with the >=20 floor) are baked with the existing `stage_trends` into `all/rating/<code>/json/`. The frontend reads that slice's trend/year files when `rating=` is set, drops years < 1968, and never falls back to the SQL engine for rated views.

**Tech Stack:** Python 3 + DuckDB + requests (pipeline, pytest via `uv`), React + TypeScript + vitest (app), rclone -> Cloudflare R2, GitHub Actions auto-deploy.

Spec: `docs/superpowers/specs/2026-09-24-mpaa-rating-filter-design.md`.

## Global Constraints

- Rating codes (URL values + slice dir names): `g`, `pg`, `pg13`, `r`. Labels: `G`, `PG`, `PG-13`, `R & NC-17/X` (MPAA marks - not translated). NC-17/X gets only ~5 films/year in the corpus (never enough to chart on its own), so it folds into the `r` slice (`SLICE_MEMBERS["r"] = ("r", "nc17")` in `build_rating_slice.py`) rather than getting its own option; `ratings.parquet` still keeps `nc17` as its own code.
- Buckets: `G->g, PG->pg, PG-13->pg13, R->r, NC-17->nc17, X->nc17`; NR/Unrated/anything else/missing -> no rating.
- Certification pick: US release dates with non-empty certification; prefer type 3 (theatrical), then 2 (limited), then 1 (premiere), then any other; earliest `release_date` within the chosen type.
- Rating slice `word_year`: `SUM(count)` + `COUNT(*) AS movie_count` per word+year from the slice's `words_by_movie` joined to its `movies`; keep words whose total across years is >= 20 (same floor as language slices).
- With a rating selected the chart starts at 1968 (`RATING_MIN_YEAR = 1968`); rated views never fall back to the SQL engine.
- Language filter active -> rating control disabled (rating ignored).
- All UI copy in `app/src/messages/en.json` only via `t`/`n`; never hand-edit the other 32 locale files (pre-commit hook translates; its glob misses `app/src/messages/.en-snapshot.json` - stage that manually if modified). Site copy uses " - ", never em-dashes. `<option>` elements need explicit `value`.
- Data must be live on R2 before the app PR merges.
- Worktree: `/Users/andrew/Projects/beveradb/moviewords-mpaa-ratings` (branch `feat/mpaa-rating-filter`). `pipeline/webdata` there is a symlink to the main checkout's webdata - never commit it (never `git add -A`).
- Commit messages: subject, blank line, `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` (two `-m` flags).
- App: `cd app && npm test`, `npx tsc -b`, `npm run lint` (3 pre-existing LineChart rules-of-hooks errors are expected). Pipeline: `cd pipeline && uv run pytest`.

---

### Task 1: `fetch_ratings.py` - TMDB US certifications -> `ratings.parquet`

**Files:**
- Create: `pipeline/scripts/fetch_ratings.py`
- Test: `pipeline/tests/test_fetch_ratings.py`

**Interfaces:**
- Produces: `pick_certification(us_release_dates: list[dict]) -> str | None`; `bucket(cert: str | None) -> str | None`; `build_parquet(cache: Path, out: Path) -> int`; CLI `uv run python scripts/fetch_ratings.py [--stage fetch|parquet|all] [--workers 8] [--cache DIR] [--out PATH] [--data-base URL]`. Output parquet columns `imdb_id VARCHAR, rating VARCHAR` (rated films only). Cache file per film `<cache>/<imdb_id>.json` = `{"tmdb_id": int, "us": [<TMDB release_dates entries>]}` or `null`.

- [ ] **Step 1: Write failing tests** `pipeline/tests/test_fetch_ratings.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_fetch_ratings.py -v`
Expected: FAIL (module file missing).

- [ ] **Step 3: Implement** `pipeline/scripts/fetch_ratings.py`:

```python
"""Fetch each film's US MPAA certification from TMDB and build
webdata/in/all/ratings.parquet (imdb_id, rating) for the Trends rating filter.

Per film: /find/{imdb_id} -> TMDB id, then /movie/{id}/release_dates. The raw US
release_dates entries are cached per film (resumable + incremental - re-run
after the corpus grows and only new films are fetched). The rating is the
film's CURRENT US certification (re-releases re-rate old films).

Run: cd pipeline && uv run python scripts/fetch_ratings.py [--stage fetch|parquet|all]
       [--workers 8] [--cache DIR] [--out PATH] [--data-base https://data.moviewords.org]
Requires TMDB_API_TOKEN or TMDB_API_KEY in the env.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402
import requests  # noqa: E402

from moviewords_pipeline import config  # noqa: E402
from moviewords_pipeline.tmdb import BASE, make_session  # noqa: E402

CACHE = config.WORK_DIR / "tmdb_release"
OUT = Path(__file__).resolve().parents[1] / "webdata" / "in" / "all" / "ratings.parquet"

BUCKETS = {"G": "g", "PG": "pg", "PG-13": "pg13", "R": "r", "NC-17": "nc17", "X": "nc17"}
# theatrical, limited, premiere; every other release type ranks after these
TYPE_RANK = {3: 0, 2: 1, 1: 2}


def pick_certification(us_release_dates):
    """The certification to use from a film's US release_dates entries: prefer
    theatrical, then limited, then premiere, then any type; earliest date
    within the chosen type. None when no entry carries a certification."""
    cands = [d for d in us_release_dates if (d.get("certification") or "").strip()]
    if not cands:
        return None
    best = min(cands, key=lambda d: (TYPE_RANK.get(d.get("type"), 9),
                                     d.get("release_date") or "9999"))
    return best["certification"].strip()


def bucket(cert):
    """MPAA mark -> rating code (X folds into nc17); None for NR/unrated/other."""
    return BUCKETS.get((cert or "").strip().upper())


def _get_json(session, url, **params):
    """GET with a short backoff on TMDB rate limiting (429)."""
    for attempt in range(6):
        resp = session.get(url, params=params or None, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def us_release_dates(session, imdb_id):
    """{'tmdb_id': id, 'us': [...]} or None when TMDB has no match."""
    found = _get_json(session, f"{BASE}/find/{imdb_id}", external_source="imdb_id")
    results = found.get("movie_results", [])
    if not results or results[0].get("id") is None:
        return None
    tmdb_id = results[0]["id"]
    data = _get_json(session, f"{BASE}/movie/{tmdb_id}/release_dates")
    us = [r for r in data.get("results", []) if r.get("iso_3166_1") == "US"]
    return {"tmdb_id": tmdb_id, "us": us[0].get("release_dates", []) if us else []}


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        _local.s = make_session()
    return _local.s


def fetch_one(imdb_id, cache):
    path = cache / f"{imdb_id}.json"
    if path.exists():
        return "cached"
    try:
        _write_json(path, us_release_dates(_session(), imdb_id))  # 'null' cached too
        return "ok"
    except Exception as exc:  # one film must never kill the batch
        print(f"ratings {imdb_id}: {exc}", flush=True)
        return "failed"


def load_ids(data_base):
    resp = requests.get(f"{data_base}/all/json/movies-index.json", timeout=60)
    resp.raise_for_status()
    return [m["id"] for m in resp.json()]


def fetch_all(ids, cache, workers):
    cache.mkdir(parents=True, exist_ok=True)
    counts = {}
    with ThreadPoolExecutor(workers) as pool:
        for i, status in enumerate(pool.map(lambda x: fetch_one(x, cache), ids), 1):
            counts[status] = counts.get(status, 0) + 1
            if i % 1000 == 0:
                print(f"  {i}/{len(ids)} {counts}", flush=True)
    print(f"fetch done: {counts}", flush=True)
    return counts


def build_parquet(cache, out):
    """ratings.parquet from the raw cache: one row per film with a bucketed
    rating; unrated/unmatched films are omitted. Returns the row count."""
    rows = []
    for path in sorted(Path(cache).glob("*.json")):
        data = json.loads(path.read_text())
        if not data:
            continue
        code = bucket(pick_certification(data.get("us", [])))
        if code:
            rows.append((path.stem, code))
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE r (imdb_id VARCHAR, rating VARCHAR)")
    if rows:
        con.executemany("INSERT INTO r VALUES (?, ?)", rows)
    con.execute(f"COPY (SELECT * FROM r ORDER BY imdb_id) TO '{out}' (FORMAT parquet)")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["fetch", "parquet", "all"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--data-base", default="https://data.moviewords.org")
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    if args.stage in ("fetch", "all"):
        fetch_all(load_ids(args.data_base), cache, args.workers)
    if args.stage in ("parquet", "all"):
        print(f"wrote {build_parquet(cache, out)} rated films -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `cd pipeline && uv run pytest tests/test_fetch_ratings.py -v`
Expected: 5 passed.

- [ ] **Step 5: Smoke-test live on 3 films** (needs `TMDB_API_KEY`; source `/Users/andrew/Projects/beveradb/moviewords/.envrc`):

```bash
cd pipeline && uv run python - <<'EOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("fr", "scripts/fetch_ratings.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from moviewords_pipeline.tmdb import make_session
s = make_session()
for i in ["tt0064115", "tt0993846", "tt0031381"]:  # Butch Cassidy, Wolf of Wall Street, Gone with the Wind
    d = m.us_release_dates(s, i); print(i, m.bucket(m.pick_certification(d["us"])) if d else None)
EOF
```
Expected: three lines with plausible codes (e.g. `pg`/`r`/`g`) - record them in the report.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/fetch_ratings.py pipeline/tests/test_fetch_ratings.py
git commit -m "feat(pipeline): fetch US MPAA certifications from TMDB into ratings.parquet" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Per-rating slices + bake + upload rules

**Files:**
- Create: `pipeline/scripts/build_rating_slice.py`, `pipeline/scripts/bake_all_ratings.py`
- Modify: `pipeline/scripts/rebuild_web_data.py` (`set_corpus` + `--rating`), `pipeline/scripts/upload_r2.sh`
- Test: `pipeline/tests/test_build_rating_slice.py`

**Interfaces:**
- Consumes: `webdata/in/all/ratings.parquet` (`imdb_id, rating`) from Task 1.
- Produces: `RATING_CODES = ("g", "pg", "pg13", "r", "nc17")`; `build_rating_slice(all_in: Path, out_in: Path, ratings: Path, code: str) -> int`; `rebuild_web_data.set_corpus(corpus, lang=None, rating=None)` -> `in|out/all/rating/<code>`; CLI `rebuild_web_data.py --corpus all --rating <code> --stage trends`; `bake_all_ratings.py` builds + bakes all five.

- [ ] **Step 1: Write failing tests** `pipeline/tests/test_build_rating_slice.py`:

```python
import duckdb
import pytest

from scripts_path import add_scripts_to_path  # noqa: F401


def _fixture(tmp_path):
    all_in = tmp_path / "in" / "all"
    all_in.mkdir(parents=True)
    con = duckdb.connect()
    con.sql(f"""
        COPY (SELECT * FROM (VALUES
            ('tt1', 'A', 1990, 1000), ('tt2', 'B', 1990, 900),
            ('tt3', 'C', 1995, 800), ('tt4', 'D', 1995, 700))
            t(imdb_id, title, year, total_words))
        TO '{all_in}/movies.parquet' (FORMAT parquet);
        COPY (SELECT * FROM (VALUES
            ('tt1', 'fuck', 15), ('tt2', 'fuck', 10), ('tt3', 'fuck', 30),
            ('tt1', 'rare', 5), ('tt4', 'fuck', 99))
            t(imdb_id, word, count))
        TO '{all_in}/words_by_movie.parquet' (FORMAT parquet);
        COPY (SELECT * FROM (VALUES ('tt1', 'r'), ('tt2', 'r'), ('tt3', 'r'), ('tt4', 'pg'))
            t(imdb_id, rating))
        TO '{all_in}/ratings.parquet' (FORMAT parquet);
    """)
    return all_in


def test_build_rating_slice_filters_films_and_rederives_word_year(tmp_path):
    from build_rating_slice import build_rating_slice
    all_in = _fixture(tmp_path)
    out_in = all_in / "rating" / "r"
    n = build_rating_slice(all_in, out_in, all_in / "ratings.parquet", "r")
    assert n == 3
    assert duckdb.sql(f"SELECT imdb_id FROM '{out_in}/movies.parquet' ORDER BY 1").fetchall() == \
        [("tt1",), ("tt2",), ("tt3",)]
    assert duckdb.sql(f"SELECT count(*) FROM '{out_in}/words_by_movie.parquet'").fetchone()[0] == 4
    # 'rare' (total 5) is under the >=20 floor; 'fuck' kept with per-year sums + film counts
    assert duckdb.sql(
        f"SELECT word, year, count, movie_count FROM '{out_in}/word_year.parquet' ORDER BY word, year"
    ).fetchall() == [("fuck", 1990, 25, 2), ("fuck", 1995, 30, 1)]


def test_build_rating_slice_rejects_unknown_code(tmp_path):
    from build_rating_slice import build_rating_slice
    all_in = _fixture(tmp_path)
    with pytest.raises(ValueError):
        build_rating_slice(all_in, all_in / "rating" / "x", all_in / "ratings.parquet", "x")


def test_set_corpus_rating_points_at_rating_subtree():
    import rebuild_web_data as rwd
    rwd.set_corpus("all", rating="pg13")
    assert rwd.IN.parts[-3:] == ("all", "rating", "pg13")
    assert rwd.OUT.parts[-3:] == ("all", "rating", "pg13")
    rwd.set_corpus("en")  # reset for other tests
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_build_rating_slice.py -v`
Expected: FAIL (module missing / unexpected keyword `rating`).

- [ ] **Step 3: Implement** `pipeline/scripts/build_rating_slice.py`:

```python
"""Build one MPAA rating's scoped input tree from the published all/ parquets +
ratings.parquet (fetch_ratings.py), so rebuild_web_data's trends stage can bake
per-rating trend JSONs. See docs/superpowers/specs/2026-09-24-mpaa-rating-filter-design.md.

  uv run python scripts/build_rating_slice.py --rating r
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

RATING_CODES = ("g", "pg", "pg13", "r", "nc17")


def build_rating_slice(all_in: Path, out_in: Path, ratings: Path, code: str) -> int:
    if code not in RATING_CODES:
        raise ValueError(f"unknown rating code {code!r}")
    out_in.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql(f"""
        CREATE TABLE movies AS
            SELECT m.* FROM '{all_in}/movies.parquet' m
            JOIN '{ratings}' r USING (imdb_id)
            WHERE r.rating = '{code}';
        CREATE TABLE wc AS
            SELECT w.* FROM '{all_in}/words_by_movie.parquet' w
            WHERE w.imdb_id IN (SELECT imdb_id FROM movies);
    """)
    con.sql(f"COPY movies TO '{out_in}/movies.parquet' (FORMAT parquet)")
    con.sql(f"""
        COPY (SELECT * FROM wc ORDER BY imdb_id, count DESC)
        TO '{out_in}/words_by_movie.parquet' (FORMAT parquet)
    """)
    # no per-rating pre-aggregate exists (unlike word_year_lang), so derive
    # word_year from the slice's own word counts, with the same per-word >=20
    # corpus floor the whole-corpus + language word_year use.
    con.sql(f"""
        COPY (
            SELECT w.word, m.year, SUM(w.count)::BIGINT AS count,
                   COUNT(*)::BIGINT AS movie_count
            FROM wc w JOIN movies m USING (imdb_id)
            WHERE m.year IS NOT NULL
            GROUP BY w.word, m.year
            QUALIFY SUM(SUM(w.count)) OVER (PARTITION BY w.word) >= 20
            ORDER BY w.word, m.year
        ) TO '{out_in}/word_year.parquet' (FORMAT parquet)
    """)
    return con.sql("SELECT COUNT(*) FROM movies").fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rating", required=True, choices=RATING_CODES)
    ap.add_argument("--webdata", default=str(Path(__file__).resolve().parent.parent / "webdata"))
    args = ap.parse_args()
    all_in = Path(args.webdata) / "in" / "all"
    n = build_rating_slice(all_in, all_in / "rating" / args.rating,
                           all_in / "ratings.parquet", args.rating)
    print(f"wrote {n} films for rating {args.rating}")


if __name__ == "__main__":
    main()
```

`pipeline/scripts/bake_all_ratings.py`:

```python
"""Build + bake every MPAA rating slice (trends stage only: per-word trend JSONs,
year-totals.json, year-films.json) under webdata/out/all/rating/<code>/.
Assumes webdata/in/all/ holds the published inputs + ratings.parquet.

  uv run python scripts/bake_all_ratings.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_rating_slice as slice_mod  # noqa: E402
import rebuild_web_data as rwd  # noqa: E402

WEBDATA = Path(__file__).resolve().parent.parent / "webdata"


def main():
    all_in = WEBDATA / "in" / "all"
    for code in slice_mod.RATING_CODES:
        t0 = time.time()
        n = slice_mod.build_rating_slice(all_in, all_in / "rating" / code,
                                         all_in / "ratings.parquet", code)
        rwd.set_corpus("all", rating=code)
        rwd.OUT.mkdir(parents=True, exist_ok=True)
        rwd.stage_trends(rwd.connect())
        print(f"  {code}: {n} films, baked in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
```

In `pipeline/scripts/rebuild_web_data.py`, replace `set_corpus` with:

```python
def set_corpus(corpus, lang=None, rating=None):
    """Point IN/OUT at the corpus subtree. 'en' keeps the historical flat
    layout; 'all' nests under all/; a lang nests under all/lang/<code>/ and an
    MPAA rating under all/rating/<code>/, mirroring the bucket prefix."""
    global IN, OUT
    sub = () if corpus == "en" else ("all",)
    if lang:
        sub = ("all", "lang", lang)
    if rating:
        sub = ("all", "rating", rating)
    IN = ROOT.joinpath("in", *sub)
    OUT = ROOT.joinpath("out", *sub)
```

and in `main()` add `ap.add_argument("--rating", default=None)` after the `--lang` argument and change the call to `set_corpus(args.corpus, lang=args.lang, rating=args.rating)`.

- [ ] **Step 4: Upload rules** - in `pipeline/scripts/upload_r2.sh`, in the first `rclone copy` (`max-age=3600`) add after the `year-films` include line:

```bash
  --filter '+ all/rating/*/json/trend/**' --filter '+ all/rating/*/json/year-totals.json' --filter '+ all/rating/*/json/year-films.json' \
```

and in the second (`max-age=300`) after its `year-films` exclude line:

```bash
  --filter '- all/rating/*/json/trend/**' --filter '- all/rating/*/json/year-totals.json' --filter '- all/rating/*/json/year-films.json' \
```

- [ ] **Step 5: Run tests**

Run: `cd pipeline && uv run pytest tests/test_build_rating_slice.py tests/test_stage_trends.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/build_rating_slice.py pipeline/scripts/bake_all_ratings.py pipeline/scripts/rebuild_web_data.py pipeline/scripts/upload_r2.sh pipeline/tests/test_build_rating_slice.py
git commit -m "feat(pipeline): per-MPAA-rating trend slices + bake + upload rules" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend data layer - rating-aware loaders + URL helpers

**Files:**
- Modify: `app/src/lib/data.ts` (add `ratingUrl`), `app/src/lib/trends.ts`, `app/src/lib/series.ts`, `app/src/views/Trends.tsx` (only the `trendsHref` call sites, to keep it compiling)
- Test: `app/src/lib/trends.test.ts`, `app/src/lib/series.test.ts`

**Interfaces:**
- Produces (exact):
  - `data.ts`: `export const ratingUrl = (code: string, path: string) => \`${DATA_BASE}/all/rating/${code}/${path}\``
  - `trends.ts`: `RATINGS` (readonly `{ code, label }[]`), `type RatingCode = 'g' | 'pg' | 'pg13' | 'r' | 'nc17'`, `RATING_MIN_YEAR = 1968`, `ratingFromParams(params: URLSearchParams): RatingCode | null`, `ratingLabel(code: RatingCode): string`, `filmsSince(films: Map<number, number>, minYear: number): number`, `interface TrendsLinkOpts { perFilm?: boolean; rating?: RatingCode | null }`, `trendsHref(words: string[], opts?: TrendsLinkOpts): string` (**signature change** from `(words, perFilm: boolean)`).
  - `series.ts`: `bakedYearFilms(rating?: RatingCode | null)`, `loadTrends(words: string[], colors: string[], rating?: RatingCode | null): Promise<TrendsData>`.

- [ ] **Step 1: Write failing tests.** In `app/src/lib/trends.test.ts` add `RATINGS, RATING_MIN_YEAR, ratingFromParams, ratingLabel, filmsSince` to the import from `./trends`, and **replace** the existing `describe('trendsHref / isPerFilm', ...)` block with:

```ts
describe('trendsHref / isPerFilm', () => {
  it('builds a linkable URL, adding per=film and rating only when set', () => {
    expect(trendsHref(['fuck', "don't"])).toBe(`/trends?w=${encodeURIComponent("fuck,don't")}`)
    expect(trendsHref(['fuck'], { perFilm: true })).toBe('/trends?w=fuck&per=film')
    expect(trendsHref(['fuck'], { rating: 'pg13' })).toBe('/trends?w=fuck&rating=pg13')
    expect(trendsHref(['fuck'], { perFilm: true, rating: 'r' })).toBe('/trends?w=fuck&per=film&rating=r')
    expect(trendsHref(['fuck'], { perFilm: false, rating: null })).toBe('/trends?w=fuck')
  })
  it('reads the per param', () => {
    expect(isPerFilm(new URLSearchParams('w=a&per=film'))).toBe(true)
    expect(isPerFilm(new URLSearchParams('w=a'))).toBe(false)
  })
})

describe('ratings', () => {
  it('lists the five MPAA buckets in order with display labels', () => {
    expect(RATINGS.map((r) => r.code)).toEqual(['g', 'pg', 'pg13', 'r', 'nc17'])
    expect(ratingLabel('pg13')).toBe('PG-13')
    expect(ratingLabel('nc17')).toBe('NC-17/X')
    expect(RATING_MIN_YEAR).toBe(1968)
  })
  it('accepts only known rating codes from the URL', () => {
    expect(ratingFromParams(new URLSearchParams('rating=pg'))).toBe('pg')
    expect(ratingFromParams(new URLSearchParams('rating=PG'))).toBeNull()
    expect(ratingFromParams(new URLSearchParams('rating=xxx'))).toBeNull()
    expect(ratingFromParams(new URLSearchParams(''))).toBeNull()
  })
  it('counts films released from a year onwards', () => {
    expect(filmsSince(new Map([[1960, 5], [1968, 2], [1990, 3]]), 1968)).toBe(5)
  })
})
```

In `app/src/lib/series.test.ts`, add `loadTrends` to the `./series` import and append:

```ts
describe('rating-scoped loaders', () => {
  const byUrl = (map: Record<string, unknown>) =>
    vi.fn(async (url: string) => {
      const hit = Object.entries(map).find(([k]) => String(url).endsWith(k))
      return hit ? new Response(JSON.stringify(hit[1])) : new Response('nope', { status: 404 })
    })

  it('reads year-films from the rating slice', async () => {
    const f = byUrl({ '/all/rating/pg/json/year-films.json': { '1990': 4 } })
    vi.stubGlobal('fetch', f)
    expect([...(await bakedYearFilms('pg'))]).toEqual([[1990, 4]])
    expect(String(f.mock.calls[0][0])).toMatch(/\/all\/rating\/pg\/json\/year-films\.json$/)
  })

  it('reads trend + totals from the rating slice and drops pre-1968 years', async () => {
    vi.stubGlobal('fetch', byUrl({
      '/all/rating/r/json/year-totals.json': { '1960': 500_000, '1970': 500_000 },
      '/all/rating/r/json/trend/fuck.json': { line: [[1960, 5], [1970, 7]], top: [], byYear: [] },
    }))
    const { wordSeries, baked } = await loadTrends(['fuck'], ['c1'], 'r')
    expect(baked).toBe(true)
    expect(wordSeries.series[0].points.map((p) => p.x)).toEqual([1970])
    expect(wordSeries.plottedYears).toEqual([1970])
  })

  it('does not fall back to the SQL engine for a rated view', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })))
    await expect(loadTrends(['fuck'], ['c1'], 'g')).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app && npx vitest run src/lib/trends.test.ts src/lib/series.test.ts`
Expected: FAIL (missing exports / wrong href).

- [ ] **Step 3: Implement.**

`app/src/lib/data.ts` - after `langUrl`:

```ts
/** A per-MPAA-rating slice (Trends only): all/rating/<code>/... */
export const ratingUrl = (code: string, path: string) => `${DATA_BASE}/all/rating/${code}/${path}`
```

`app/src/lib/trends.ts` - replace the existing `trendsHref` with, and add:

```ts
/** MPAA rating filter (Trends only). Codes are the URL values + slice dir
 * names; labels are MPAA marks (not translated). X folds into NC-17. */
export const RATINGS = [
  { code: 'g', label: 'G' },
  { code: 'pg', label: 'PG' },
  { code: 'pg13', label: 'PG-13' },
  { code: 'r', label: 'R' },
  { code: 'nc17', label: 'NC-17/X' },
] as const

export type RatingCode = (typeof RATINGS)[number]['code']

/** MPAA ratings began Nov 1968; earlier films only carry later re-release
 * ratings (a biased "re-released classics" sample), so rated charts start here. */
export const RATING_MIN_YEAR = 1968

export function ratingFromParams(params: URLSearchParams): RatingCode | null {
  const r = params.get('rating')
  return RATINGS.some((x) => x.code === r) ? (r as RatingCode) : null
}

export const ratingLabel = (code: RatingCode): string =>
  RATINGS.find((r) => r.code === code)?.label ?? code

/** Films released in or after `minYear` (the rated-films count in the note). */
export const filmsSince = (films: Map<number, number>, minYear: number): number =>
  [...films].reduce((sum, [y, n]) => (y >= minYear ? sum + n : sum), 0)

export interface TrendsLinkOpts {
  perFilm?: boolean
  rating?: RatingCode | null
}

/** Trends URL for a word list; `per=film` / `rating=` only when set, so
 * default links stay unchanged. */
export const trendsHref = (words: string[], opts: TrendsLinkOpts = {}): string =>
  `/trends?w=${encodeURIComponent(words.join(','))}` +
  `${opts.perFilm ? '&per=film' : ''}${opts.rating ? `&rating=${opts.rating}` : ''}`
```

`app/src/lib/series.ts`:
- import `ratingUrl` from `./data` (add to the existing import) and `RATING_MIN_YEAR, type RatingCode` from `./trends` (add to the existing import list).
- Replace `bakedYearMap` + the two consts after it with:

```ts
/** A pre-baked per-year number map (a couple of KB), cached for the session.
 * A rating -> that MPAA slice's file (language filter not combined - the UI
 * prevents it); else 0 languages -> the global file, 1+ -> fetch + sum the
 * selected languages' files. year-totals.json = words per year (rate
 * denominator); year-films.json = films per year (per-film denominator). */
function bakedYearMap(
  file: 'year-totals.json' | 'year-films.json',
  rating: RatingCode | null = null,
): Promise<Map<number, number>> {
  const langs = rating ? [] : activeLanguages()
  const key = `${file}|${rating ? `rating:${rating}` : langs.join(',')}`
  const hit = yearMapCache.get(key)
  if (hit) return hit
  const p = (async () => {
    if (rating) {
      const res = await fetch(ratingUrl(rating, `json/${file}`))
      if (!res.ok) throw new Error(`${res.status} fetching ${file} [rating ${rating}]`)
      return toYearMap(await res.json())
    }
    if (!langs.length) return toYearMap(await fetchJSON<Record<string, number>>(`json/${file}`))
    const maps = await Promise.all(
      langs.map(async (code) => {
        const res = await fetch(langUrl(code, `json/${file}`))
        if (!res.ok) throw new Error(`${res.status} fetching ${file} [${code}]`)
        return toYearMap(await res.json())
      }),
    )
    return mergeYearTotals(maps)
  })()
  // a failed fetch must not be cached forever
  p.catch(() => yearMapCache.delete(key))
  yearMapCache.set(key, p)
  return p
}

const bakedYearTotals = (rating: RatingCode | null = null) => bakedYearMap('year-totals.json', rating)

/** Films released per year (language- or rating-scoped) - the per-film denominator. */
export const bakedYearFilms = (rating: RatingCode | null = null) => bakedYearMap('year-films.json', rating)
```

- In `fetchTrendFile`, change the signature to `async function fetchTrendFile(word: string, rating: RatingCode | null = null)` and insert right after `const key = wordKey(word)`:

```ts
  if (rating) {
    const res = await fetch(ratingUrl(rating, `json/trend/${key}.json`))
    if (res.status === 404) return null
    if (!res.ok) throw new Error(`${res.status} fetching trend/${word} [rating ${rating}]`)
    return res.json() as Promise<TrendFile>
  }
```

- In `loadTrends`: signature `export async function loadTrends(words: string[], colors: string[], rating: RatingCode | null = null): Promise<TrendsData>`; use `bakedYearTotals(rating)` and `Promise.all(words.map((w) => fetchTrendFile(w, rating)))`; after building `rows`, add

```ts
    // rated charts start at 1968 (MPAA ratings began then; earlier films only
    // carry later re-release ratings)
    const kept = rating ? rows.filter((r) => r.year >= RATING_MIN_YEAR) : rows
```

  and pass `kept` (not `rows`) to `toSeries`. In the `catch`, before the `console.warn`, add:

```ts
    // the engine can't filter by rating - surface the error instead of
    // silently charting the whole corpus
    if (rating) throw e
```

  and update the doc comment above `loadTrends` to mention the rating path.

`app/src/views/Trends.tsx` - update the 4 existing `trendsHref(...)` call sites to the options form, e.g. `trendsHref(words.filter((x) => x !== w), { perFilm })`, `trendsHref([w], { perFilm })`, `trendsHref([...new Set([...words, w])].slice(0, MAX_WORDS), { perFilm })`, and the toggle `trendsHref(words, { perFilm: on })`. (Task 4 adds `rating` to these.)

- [ ] **Step 4: Run tests**

Run: `cd app && npx vitest run src/lib/trends.test.ts src/lib/series.test.ts && npm test && npx tsc -b`
Expected: all pass, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/data.ts app/src/lib/trends.ts app/src/lib/series.ts app/src/views/Trends.tsx app/src/lib/trends.test.ts app/src/lib/series.test.ts
git commit -m "feat(trends): rating-scoped trend loaders + rating URL helpers" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Trends page - rating selector, notes, copy

**Files:**
- Modify: `app/src/views/Trends.tsx`, `app/src/messages/en.json` (locales regenerate via hook)

**Interfaces:**
- Consumes: `RATINGS`, `RatingCode`, `RATING_MIN_YEAR`, `ratingFromParams`, `ratingLabel`, `filmsSince`, `trendsHref(words, { perFilm, rating })` (Task 3); `bakedYearFilms(rating)`, `loadTrends(words, colors, rating)` (Task 3).

- [ ] **Step 1: Copy** - add to the `"trends"` object in `app/src/messages/en.json` (after `"perFilmSummary"`):

```json
    "ratingLabel": "Rating",
    "allRatings": "All ratings",
    "ratingNeedsAllFilms": "Rating filter works with All films",
    "ratingNote": "Based on {count} {rating}-rated films (current US MPAA rating, via TMDB).",
    "ratingSince1968": "MPAA ratings began in November 1968 - earlier films are only rated from later re-releases, so the chart starts in 1968.",
```

- [ ] **Step 2: Wire the view** (`app/src/views/Trends.tsx`):

Imports: add `RATINGS, RATING_MIN_YEAR, ratingFromParams, ratingLabel, filmsSince, type RatingCode` to the `../lib/trends` import.

After `const perFilm = isPerFilm(params)`:

```tsx
  // rating filter (Trends only); ignored while a language filter is active
  const rating: RatingCode | null = langs.length ? null : ratingFromParams(params)
```

Replace the films effect with (reload when the rating changes; clear stale values first):

```tsx
  useEffect(() => {
    let cancelled = false
    setFilms(null)
    setFilmsError(null)
    bakedYearFilms(rating)
      .then((f) => !cancelled && setFilms(f))
      .catch((e) => !cancelled && setFilmsError(String(e)))
    return () => {
      cancelled = true
    }
  }, [rating])
```

In the data effect, change `loadTrends(chartWords, COLORS)` to `loadTrends(chartWords, COLORS, rating)` and its dependency list `[wordsKey]` to `[wordsKey, rating]`.

Every `trendsHref(..., { perFilm })` call gains `rating`: `{ perFilm, rating }`; the per-film toggle becomes `trendsHref(words, { perFilm: on, rating })`.

Below the existing `languageNote` paragraph add:

```tsx
      {rating && films && (
        <p className="mt-1 text-sm text-ink-2">
          {t('trends.ratingNote', { count: n(filmsSince(films, RATING_MIN_YEAR)), rating: ratingLabel(rating) })}{' '}
          {t('trends.ratingSince1968')}
        </p>
      )}
```

Replace the per-film toggle `<div className="mb-3 flex gap-1" role="group" ...>...</div>` with a controls row holding the toggle and (for user-word charts only) the rating select:

```tsx
          <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="flex gap-1" role="group" aria-label={t('trends.measureAriaLabel')}>
              {/* keep the existing two toggle buttons here unchanged, except trendsHref(words, { perFilm: on, rating }) */}
            </div>
            {!featured && (
              <label className="flex items-center gap-1.5 font-script text-xs">
                {t('trends.ratingLabel')}
                <select
                  value={rating ?? ''}
                  disabled={langs.length > 0}
                  onChange={(e) => navigate(trendsHref(words, { perFilm, rating: (e.target.value || null) as RatingCode | null }))}
                  className="border-2 border-ink bg-card px-1.5 py-1 font-script text-xs disabled:opacity-50"
                >
                  <option value="">{t('trends.allRatings')}</option>
                  {RATINGS.map((r) => (
                    <option key={r.code} value={r.code}>{r.label}</option>
                  ))}
                </select>
                {langs.length > 0 && <span className="text-ink-3">{t('trends.ratingNeedsAllFilms')}</span>}
              </label>
            )}
          </div>
```

(The toggle buttons' markup/classes stay exactly as they are today; only their `onClick` gains `rating`.)

- [ ] **Step 3: Verify** - `cd app && npx tsc -b && npm run lint && npm test` (only the 3 pre-existing LineChart lint errors).

- [ ] **Step 4: Commit** (pre-commit hook translates; stage `app/src/messages/.en-snapshot.json` too if it shows modified, and amend)

```bash
git add app/src/views/Trends.tsx app/src/messages/en.json
git commit -m "feat(trends): MPAA rating filter UI" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git status --short   # if app/src/messages/.en-snapshot.json is modified: git add it && git commit --amend --no-edit
cd app && npm run translate:validate
```

(The controller does the browser check.)

---

### Task 5: Ops - fetch ratings, bake slices, upload (controller)

- [ ] Run the fetch in the main checkout's cache dir (so it survives worktree removal): `cd pipeline && uv run python scripts/fetch_ratings.py --stage all --workers 8 --cache /Users/andrew/Projects/beveradb/moviewords/data/work/tmdb_release` (~30-40 min). Check the rated count and bucket spread (`SELECT rating, count(*) FROM 'webdata/in/all/ratings.parquet' GROUP BY 1`).
- [ ] `uv run python scripts/bake_all_ratings.py`; confirm `webdata/out/all/rating/{g,pg,pg13,r,nc17}/json/{year-totals,year-films}.json` + `trend/` exist and counts look sane (`ls .../trend | wc -l`).
- [ ] Upload only rating files with rclone (R2 creds derived from `MOVIEWORDS_CF_TOKEN`): filters `+ all/rating/*/json/trend/**`, `+ all/rating/*/json/year-totals.json`, `+ all/rating/*/json/year-films.json`, `- *`, `Cache-Control: public, max-age=3600`.
- [ ] Verify 200 + CORS for `all/rating/r/json/year-films.json` and `all/rating/pg/json/trend/fuck.json`.

### Task 6: Ship (controller)

- [ ] Playwright on `localhost:5173`: `#/trends?w=fuck&rating=pg` (note + chart from 1968), `&per=film`, switch ratings via the select (URL updates, data reloads), language filter disables the select, featured hides it, 390px no overflow.
- [ ] Final whole-branch review; PR (no `@coderabbitai ignore` - CodeRabbit CLI is SSO-blocked); squash-merge; watch deploy; prod check; hand the user a Reddit follow-up for u/hipsterdoofus.
- [ ] Add the "pre-1968 rated films" investigation to `docs/handoffs/2026-09-24-launch-feedback-followups.md`.
