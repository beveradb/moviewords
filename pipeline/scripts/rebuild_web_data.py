#!/usr/bin/env python
"""Rebuild published web data from the already-published parquets — no VM, no
raw subtitles. Regenerates:

  meta        word_meta.parquet (adds pos, dist) + json/leaderboard-default.json
  movies      json/movie/*.json (word rows gain pos)
  boards      json/leaderboards/{shifts,films,wonders,everywhere}.json
  signatures  json/signature/{decades,genres}.json (adds stats + top500)
  featured    json/featured-series.json (homepage chart without the SQL engine)
  trends      json/trend/<key>.json per word + json/year-totals.json (Trends
              page bake, no client SQL engine)
  yearfilms   json/year-films.json only (films per year; also written by trends)

Usage:
  scripts/fetch_published.sh [en|all]   # once, mirrors inputs to webdata/in[/all]
  uv run python scripts/rebuild_web_data.py [--corpus en|all] [--stage all|meta|movies|boards|signatures|featured|trends]

Outputs land in webdata/out mirroring the R2 layout; publish with
scripts/upload_r2.sh (additive copy + Cache-Control + edge purge), then
deploy the app.
"""

import argparse
import json
import re
import time
from pathlib import Path

import duckdb

from moviewords_pipeline import boards
from moviewords_pipeline.derive import load_profanity, load_stopwords, log_odds, word_meta
from moviewords_pipeline.signatures_ext import extend_signatures

ROOT = Path(__file__).resolve().parent.parent / "webdata"
IN, OUT = ROOT / "in", ROOT / "out"


def set_corpus(corpus, lang=None):
    """Point IN/OUT at the corpus subtree. 'en' keeps the historical flat
    layout; 'all' nests under all/; a lang nests under all/lang/<code>/
    mirroring the bucket prefix."""
    global IN, OUT
    sub = () if corpus == "en" else ("all",)
    if lang:
        sub = ("all", "lang", lang)
    IN = ROOT.joinpath("in", *sub)
    OUT = ROOT.joinpath("out", *sub)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.sql(f"CREATE VIEW movies AS SELECT * FROM '{IN / 'movies.parquet'}'")
    con.sql(f"CREATE VIEW words_by_movie AS SELECT * FROM '{IN / 'words_by_movie.parquet'}'")
    con.sql(f"CREATE VIEW word_year AS SELECT * FROM '{IN / 'word_year.parquet'}'")
    return con


def build_full_meta(con):
    """[(word, count, movie_count)] plus {word: (zipf, classes, pos, dist)}."""
    rows = con.sql("""
        SELECT word, SUM(count)::BIGINT AS c, COUNT(DISTINCT imdb_id) AS mc
        FROM words_by_movie GROUP BY word ORDER BY c DESC
    """).fetchall()
    return rows, word_meta({w: c for w, c, _ in rows})


def load_meta_parquet(con):
    rows = con.sql(f"SELECT word, zipf, classes, pos, dist FROM '{OUT / 'word_meta.parquet'}'").fetchall()
    return {w: (z, c, p, d) for w, z, c, p, d in rows}


def stage_meta(con):
    rows, meta = build_full_meta(con)
    con.sql("CREATE TABLE wm (word VARCHAR, zipf DOUBLE, classes VARCHAR, pos VARCHAR, dist DOUBLE)")
    con.executemany("INSERT INTO wm VALUES (?, ?, ?, ?, ?)",
                    [(w, *meta[w]) for w, _, _ in rows])
    con.sql(f"COPY (SELECT * FROM wm ORDER BY word) TO '{OUT / 'word_meta.parquet'}' (FORMAT parquet)")

    stop = load_stopwords()
    (OUT / "json").mkdir(parents=True, exist_ok=True)
    (OUT / "json" / "leaderboard-default.json").write_text(json.dumps({
        "words": [[w, c, mc, *meta[w]] for w, c, mc in rows if w not in stop][:1000],
        "stopwords": [[w, c, mc, *meta[w]] for w, c, mc in rows if w in stop][:50],
    }))


def stage_movies(con):
    """Streaming re-derive of every per-movie JSON with pos-tagged word rows.
    One pass over the (imdb_id, count DESC)-sorted parquet — never per-movie
    queries (see docs/ARCHITECTURE.md on the sort-order contract).
    """
    meta = load_meta_parquet(con)
    stop = load_stopwords()
    corpus = dict(con.sql("SELECT word, SUM(count) FROM words_by_movie GROUP BY word").fetchall())
    n_corpus = sum(corpus.values())
    movie_cols = ["imdb_id", "title", "year", "total_words", "unique_words", "words_per_minute"]
    movies = {r[0]: dict(zip(movie_cols, r)) for r in
              con.sql(f"SELECT {', '.join(movie_cols)} FROM movies").fetchall()}
    (OUT / "json" / "movie").mkdir(parents=True, exist_ok=True)

    def tag(word, value):
        z, cls, pos, _ = meta.get(word, (0.0, "x", "x", 0.0))
        return [word, value, z, cls, pos]

    def flush(imdb_id, rows):
        m = movies.get(imdb_id)
        if m is None:
            return
        payload = {
            "imdb_id": m["imdb_id"], "title": m["title"], "year": m["year"],
            "stats": {"total_words": m["total_words"], "unique_words": m["unique_words"],
                      "words_per_minute": m["words_per_minute"]},
            "top": [tag(w, c) for w, c in rows if w not in stop][:200],
            "top_all": [tag(w, c) for w, c in rows][:50],
            "distinctive": [tag(w, round(z, 2))
                            for w, z in log_odds(dict(rows), corpus, n_corpus=n_corpus)[:50]],
        }
        (OUT / "json" / "movie" / f"{imdb_id}.json").write_text(json.dumps(payload))

    cur = con.execute(f"SELECT imdb_id, word, count FROM '{IN / 'words_by_movie.parquet'}'")
    current, rows, n = None, [], 0
    while batch := cur.fetchmany(1_000_000):
        for imdb_id, word, count in batch:
            if imdb_id != current:
                if current is not None:
                    flush(current, rows)
                    n += 1
                current, rows = imdb_id, []
            rows.append((word, count))
    if current is not None:
        flush(current, rows)
        n += 1
    print(f"  wrote {n} movie JSONs")


def stage_boards(con):
    out = OUT / "json" / "leaderboards"
    out.mkdir(parents=True, exist_ok=True)
    meta = load_meta_parquet(con)

    def quality(word):
        # drop OCR junk: unknown-POS words that everyday English barely knows
        zipf, _, pos, _ = meta.get(word, (0.0, "x", "x", 0.0))
        return pos in "nvar" or zipf >= 4.0

    (out / "shifts.json").write_text(json.dumps(
        boards.risers_fallers(con, quality=quality)))
    (out / "films.json").write_text(json.dumps(
        boards.film_superlatives(con, load_profanity())))
    (out / "wonders.json").write_text(json.dumps(boards.one_film_wonders(con)))
    (out / "everywhere.json").write_text(json.dumps(
        boards.ubiquity(con, exclude=load_stopwords())))


def stage_signatures(con):
    profanity = load_profanity()
    out = OUT / "json" / "signature"
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("decades", "genres"):
        sig = json.loads((IN / "signature" / f"{kind}.json").read_text())
        (out / f"{kind}.json").write_text(
            json.dumps(extend_signatures(con, sig, kind, profanity)))


FEATURED_TS = Path(__file__).resolve().parents[2] / "app" / "src" / "lib" / "featured.ts"


def featured_words():
    """Union of every word in app/src/lib/featured.ts FEATURED, parsed from the
    source so the bake can't drift from the app. The app falls back to a live
    DuckDB query for any word missing from the bake, so a stale file degrades
    gracefully instead of breaking the homepage chart."""
    src = FEATURED_TS.read_text()
    block = src.split("export const FEATURED")[1].split("export const MATCHUPS")[0]
    words = []
    for arr in re.findall(r"words:\s*\[(.*?)\]", block, re.S):
        words += [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", arr)]
    seen = list(dict.fromkeys(words))
    if not seen:
        raise RuntimeError(f"no FEATURED words parsed from {FEATURED_TS}")
    return seen


def stage_featured(con):
    totals = con.sql("SELECT year, SUM(count)::BIGINT FROM word_year GROUP BY year").fetchall()
    words = {w: [[y, c] for y, c in con.execute(
                "SELECT year, count::BIGINT FROM word_year WHERE word = ? ORDER BY year", [w]
             ).fetchall()] for w in featured_words()}
    (OUT / "json").mkdir(parents=True, exist_ok=True)
    (OUT / "json" / "featured-series.json").write_text(json.dumps(
        {"totals": {str(y): t for y, t in totals}, "words": words}))


def write_year_films(con):
    """json/year-films.json: films released per year in this corpus/slice -
    the Trends page's per-film denominator (a word's yearly count / films)."""
    rows = con.sql(
        "SELECT year, count(*)::BIGINT FROM movies WHERE year IS NOT NULL "
        "GROUP BY year ORDER BY year").fetchall()
    (OUT / "json").mkdir(parents=True, exist_ok=True)
    (OUT / "json" / "year-films.json").write_text(
        json.dumps({str(y): n for y, n in rows}))


def stage_yearfilms(con):
    """Standalone so the 35 small files can be (re)baked + uploaded without
    regenerating ~485k per-word trend JSONs."""
    write_year_films(con)


def _word_key(w: str) -> str:
    # The object key/filename is the RAW word: the Cloudflare/R2 edge
    # percent-decodes the request path exactly once before key lookup
    # (verified live 2026-09-14: /json/trend/don%27t.json 404d against a
    # don%27t.json key while the double-encoded URL 200d), so the frontend's
    # percent-encoded URL must decode INTO the key, not equal it. Tokens are
    # lowercase letters/apostrophes (plus rare unfolded non-Latin), all safe
    # as filenames and R2 keys.
    return w


def stage_trends(con):
    """One small JSON per chartable word so the Trends page never boots the
    35MB DuckDB-WASM engine (the Firefox-Android hang). word_year is the
    source of truth for which words get a file; the window queries are
    semijoined to it so sub-threshold words don't bloat the dicts."""
    out = OUT / "json" / "trend"
    out.mkdir(parents=True, exist_ok=True)

    totals = con.sql(
        "SELECT year, SUM(count)::BIGINT FROM word_year GROUP BY year").fetchall()
    (OUT / "json" / "year-totals.json").write_text(
        json.dumps({str(y): t for y, t in totals}))
    write_year_films(con)

    line = {}
    for w, y, c in con.execute(
            "SELECT word, year, count::BIGINT FROM word_year ORDER BY word, year"
    ).fetchall():
        line.setdefault(w, []).append([y, c])

    top = {}
    for w, iid, title, yr, c, tw in con.execute("""
        SELECT word, imdb_id, title, year, count, total_words FROM (
          SELECT wm.word, wm.imdb_id, m.title, m.year,
                 wm.count::BIGINT AS count, m.total_words::BIGINT AS total_words,
                 ROW_NUMBER() OVER (PARTITION BY wm.word
                                    ORDER BY wm.count DESC, m.title) AS rn
          FROM words_by_movie wm
          JOIN movies m USING (imdb_id)
          JOIN (SELECT DISTINCT word FROM word_year) wy ON wy.word = wm.word
        ) WHERE rn <= 15 ORDER BY word, count DESC, title
    """).fetchall():
        top.setdefault(w, []).append([iid, title, yr, c, tw])

    by_year = {}
    for w, yr, iid, title, c in con.execute("""
        SELECT word, year, imdb_id, title, count FROM (
          SELECT wm.word, m.year, wm.imdb_id, m.title, wm.count::BIGINT AS count,
                 ROW_NUMBER() OVER (PARTITION BY wm.word, m.year
                                    ORDER BY wm.count DESC, m.title) AS rn
          FROM words_by_movie wm
          JOIN movies m USING (imdb_id)
          JOIN (SELECT DISTINCT word FROM word_year) wy ON wy.word = wm.word
        ) WHERE rn = 1 ORDER BY word, year
    """).fetchall():
        by_year.setdefault(w, []).append([yr, iid, title, c])

    n = 0
    for w, ln in line.items():
        payload = {"line": ln, "top": top.get(w, []), "byYear": by_year.get(w, [])}
        (out / f"{_word_key(w)}.json").write_text(
            json.dumps(payload, separators=(",", ":")))
        n += 1
    print(f"  wrote {n} trend JSONs")


STAGES = {"meta": stage_meta, "movies": stage_movies,
          "boards": stage_boards, "signatures": stage_signatures,
          "featured": stage_featured, "trends": stage_trends,
          "yearfilms": stage_yearfilms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", *STAGES])
    ap.add_argument("--corpus", default="en", choices=["en", "all"])
    ap.add_argument("--lang", default=None)
    args = ap.parse_args()
    set_corpus(args.corpus, lang=args.lang)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in STAGES if args.stage == "all" else [args.stage]:
        t0 = time.time()
        print(f"stage {name}… (corpus {args.corpus})", flush=True)
        STAGES[name](connect())
        print(f"stage {name} done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
