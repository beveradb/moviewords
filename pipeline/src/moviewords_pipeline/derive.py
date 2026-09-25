import json
import math
from importlib import resources

import duckdb

from . import config


def _load_wordlist(name):
    text = resources.files("moviewords_pipeline").joinpath(name).read_text()
    return {w.strip() for w in text.splitlines()
            if w.strip() and not w.startswith("#")}


def load_stopwords() -> set[str]:
    return _load_wordlist("stopwords_en.txt")


def load_profanity() -> set[str]:
    return _load_wordlist("profanity_en.txt")


def log_odds(movie_counts: dict[str, int], corpus_counts: dict[str, int],
             alpha0: float = 100.0, min_count: int = 3,
             n_corpus: int | None = None) -> list[tuple[str, float]]:
    """Monroe et al. log-odds-ratio with an informative Dirichlet prior drawn
    from corpus word frequencies. Returns (word, z) pairs sorted descending
    by z, i.e. words most overrepresented in `movie_counts` relative to the
    corpus come first. Callers looping over many movies should pass the
    precomputed `n_corpus` — re-summing the ~1M-entry corpus dict per movie
    dominates an otherwise-fast pass.
    """
    n_movie = sum(movie_counts.values())
    if n_corpus is None:
        n_corpus = sum(corpus_counts.values())
    out = []
    for word, y in movie_counts.items():
        if y < min_count:
            continue
        y_c = corpus_counts.get(word, 0)
        prior = alpha0 * y_c / n_corpus if n_corpus else 0
        if prior == 0:
            continue
        denom_movie = n_movie + alpha0 - y - prior
        denom_corpus = n_corpus + alpha0 - y_c - prior
        if denom_movie <= 0 or denom_corpus <= 0:
            # Degenerate only when a single word accounts for the *entire*
            # movie/corpus word count (e.g. tiny test fixtures, or a
            # language slice with one repeated word) - no real signal to
            # compute a ratio against, so skip rather than divide by <=0.
            continue
        delta = (math.log((y + prior) / denom_movie)
                 - math.log((y_c + prior) / denom_corpus))
        variance = 1.0 / (y + prior) + 1.0 / (y_c + prior)
        out.append((word, delta / math.sqrt(variance)))
    return sorted(out, key=lambda t: -t[1])


def run(corpus="en"):
    """Derive all published artifacts. corpus='en' (default) keeps the
    original_language filter and writes to data/out/; corpus='all' skips it -
    translated subtitles included, labeled - and writes to data/out/all/,
    adding word_year_lang.parquet for per-original-language trends."""
    if corpus not in ("en", "all"):
        raise ValueError(f"unknown corpus {corpus!r} - expected 'en' or 'all'")
    out = config.OUT_DIR if corpus == "en" else config.OUT_DIR / "all"
    (out / "words_by_movie").mkdir(parents=True, exist_ok=True)
    (out / "words_by_word").mkdir(parents=True, exist_ok=True)
    (out / "json" / "movie").mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    w = config.WORK_DIR
    con.sql(f"""
        CREATE VIEW curated AS SELECT * FROM '{w / "curated.parquet"}';
        CREATE VIEW stats AS SELECT * FROM '{w / "movie_stats.parquet"}';
        CREATE VIEW wc AS SELECT * FROM '{w / "word_counts.parquet"}';
        CREATE VIEW matched AS SELECT * FROM '{w / "corpus_index.parquet"}';
        CREATE TABLE tmdb AS SELECT * FROM read_json(
            '{w / "tmdb"}/*.json',
            columns={{'imdb_id': 'VARCHAR', 'countries': 'VARCHAR[]',
                      'original_language': 'VARCHAR'}}
        );
    """)
    lang_filter = (f"AND t.original_language = '{config.LANG}'"
                   if corpus == "en" else "")
    # the count stage's per-film quality tier (selection.parquet): "low"
    # films - only a machine-translated / auto-caption / possibly wrong-film
    # subtitle - are kept out of every aggregate (`movies` feeds them all)
    # but still get a film page, from the *_flagged outputs
    sel = w / "selection.parquet"
    tiers = (f"SELECT imdb_id, tier, flags FROM '{sel}'" if sel.exists() else
             "SELECT NULL::VARCHAR AS imdb_id, NULL::VARCHAR AS tier, "
             "NULL::VARCHAR AS flags WHERE false")
    con.sql(f"""
        CREATE TABLE all_movies AS
        SELECT c.imdb_id, c.title, c.year, t.countries, c.genres,
               c.runtime_minutes, c.rating, c.votes,
               s.total_words, s.unique_words, s.words_per_minute,
               t.original_language,
               COALESCE(q.tier, 'ok') AS quality,
               COALESCE(q.flags, '[]') AS quality_flags
        FROM curated c
        JOIN stats s USING (imdb_id)
        JOIN tmdb t USING (imdb_id)
        LEFT JOIN ({tiers}) q USING (imdb_id)
        WHERE true {lang_filter};
        CREATE TABLE movies AS SELECT * EXCLUDE (quality, quality_flags)
            FROM all_movies WHERE quality = 'ok';
        CREATE TABLE flagged AS SELECT * FROM all_movies WHERE quality <> 'ok';
    """)
    con.sql(f"COPY movies TO '{out / 'movies.parquet'}' (FORMAT parquet)")
    con.sql(f"COPY flagged TO '{out / 'movies_flagged.parquet'}' (FORMAT parquet)")
    (out / "words_by_movie_flagged").mkdir(parents=True, exist_ok=True)
    con.sql(f"""
        COPY (
            SELECT wc.* FROM wc JOIN flagged USING (imdb_id)
            ORDER BY imdb_id, count DESC
        ) TO '{out / "words_by_movie_flagged" / "data.parquet"}' (FORMAT parquet);
    """)

    con.sql(f"""
        COPY (
            SELECT wc.* FROM wc JOIN movies USING (imdb_id)
            ORDER BY imdb_id, count DESC
        ) TO '{out / "words_by_movie" / "data.parquet"}' (FORMAT parquet);
    """)
    con.sql(f"""
        COPY (
            SELECT wc.* FROM wc JOIN movies USING (imdb_id)
            ORDER BY word, imdb_id
        ) TO '{out / "words_by_word" / "data.parquet"}' (FORMAT parquet);
    """)
    con.sql(f"""
        COPY (
            SELECT word, year, SUM(count)::BIGINT AS count,
                   COUNT(DISTINCT wc.imdb_id) AS movie_count
            FROM wc JOIN movies USING (imdb_id)
            GROUP BY word, year
            QUALIFY SUM(SUM(count)) OVER (PARTITION BY word) >= 20
            ORDER BY word, year
        ) TO '{out / "word_year.parquet"}' (FORMAT parquet);
    """)
    if corpus == "all":
        # per-original-language trends: keep a (word, lang) pair only when its
        # corpus-wide total clears the same floor word_year uses per word
        con.sql(f"""
            COPY (
                SELECT wc.word, m.year, m.original_language AS lang,
                       SUM(wc.count)::BIGINT AS count,
                       COUNT(DISTINCT wc.imdb_id) AS movie_count
                FROM wc JOIN movies m USING (imdb_id)
                GROUP BY wc.word, m.year, m.original_language
                QUALIFY SUM(SUM(wc.count))
                    OVER (PARTITION BY wc.word, m.original_language) >= 20
                ORDER BY wc.word, lang, m.year
            ) TO '{out / "word_year_lang.parquet"}' (FORMAT parquet);
        """)

    _write_json_hot_paths(con, out)
    _write_signatures(con, out)
    _write_wordlists(out)
    _write_report(con, out, corpus)


def quality_note(tier, flags_json):
    """The movie page's `quality` field for a flagged film: its tier and why
    (asr, machine-translated, wrong-cast)."""
    return {"tier": tier, "flags": json.loads(flags_json or "[]")}


def build_signature_base(con) -> dict:
    """Compute the decade/genre log-odds signature payloads from the `movies`
    and `wc` views. Returned as {kind: {key: entry}} so callers can write it to
    a per-corpus or per-language signature/*.json base."""
    stop = load_stopwords()
    corpus = dict(con.sql(
        "SELECT word, SUM(count) FROM wc JOIN movies USING (imdb_id) GROUP BY word"
    ).fetchall())
    n_corpus = sum(corpus.values())
    kinds = {
        "decades": ("(m.year // 10) * 10",
                    "SELECT DISTINCT (year // 10) * 10 FROM movies ORDER BY 1"),
        "genres": ("g.genre",
                   "SELECT DISTINCT UNNEST(genres) FROM movies ORDER BY 1"),
    }
    out = {}
    for kind, (key_expr, keys_sql) in kinds.items():
        genre_join = ("JOIN (SELECT imdb_id, UNNEST(genres) AS genre FROM movies) g "
                      "USING (imdb_id)") if kind == "genres" else ""
        payload = {}
        for (key,) in con.sql(keys_sql).fetchall():
            if key is None:
                continue
            n_movies = con.sql(f"""
                SELECT COUNT(DISTINCT m.imdb_id) FROM movies m {genre_join}
                WHERE {key_expr} = ?
            """, params=[key]).fetchone()[0]
            # A word must appear in several distinct films to count as an entity
            # signature — otherwise one film's OCR junk ("chffffff" x400) or a
            # single character name dominates the decade/genre log-odds.
            min_films = min(3, n_movies)
            rows = con.sql(f"""
                SELECT wc.word, SUM(wc.count)::BIGINT AS c
                FROM wc JOIN movies m USING (imdb_id) {genre_join}
                WHERE {key_expr} = ? GROUP BY wc.word
                HAVING COUNT(DISTINCT wc.imdb_id) >= {min_films}
                ORDER BY c DESC
            """, params=[key]).fetchall()
            counts = dict(rows)
            payload[str(key)] = {
                "movie_count": n_movies,
                "total_words": sum(counts.values()),
                "top": [[w, c] for w, c in rows if w not in stop][:100],
                "signature": [[w, round(z, 2)]
                              for w, z in log_odds(counts, corpus, min_count=20,
                                                   n_corpus=n_corpus)[:100]],
            }
        out[kind] = payload
    return out


def _write_signatures(con, out):
    """Signature (log-odds) and top words for whole decades and genres, one
    small JSON per entity kind (see build_signature_base)."""
    base = build_signature_base(con)
    (out / "json" / "signature").mkdir(parents=True, exist_ok=True)
    for kind, payload in base.items():
        (out / "json" / "signature" / f"{kind}.json").write_text(json.dumps(payload))


def word_meta(counts: dict[str, int]):
    """Per-word metadata: (zipf, classes, pos, dist) keyed by word.

    classes: all WordNet POS letters the word can be (n/v/a/r, satellites fold
    into 'a'); kept for back-compat. pos: the single dominant POS (see
    word_meta2.dominant_pos) that powers the app's word-kind filters. dist:
    movie-distinctiveness — how over-represented the word is in film dialogue
    vs everyday English, from the corpus rate implied by `counts`. "x" classes
    = WordNet doesn't know it (names, invented words, OCR survivors).
    """
    from wordfreq import zipf_frequency

    from .word_meta2 import _wordnet, distinctiveness, dominant_pos

    wn = _wordnet()
    total = sum(counts.values()) or 1
    meta = {}
    for word, count in counts.items():
        pos_set = {s.pos() for s in wn.synsets(word)}
        if "s" in pos_set:  # adjective satellites count as adjectives
            pos_set.discard("s")
            pos_set.add("a")
        classes = "".join(sorted(pos_set)) or "x"
        zipf = round(zipf_frequency(word, "en"), 1)
        meta[word] = (zipf, classes, dominant_pos(word, zipf),
                      distinctiveness(count / total * 1e6, zipf))
    return meta


def _write_json_hot_paths(con, out):
    stop = load_stopwords()
    corpus = dict(con.sql(
        "SELECT word, SUM(count) FROM wc JOIN movies USING (imdb_id) GROUP BY word"
    ).fetchall())
    wmeta = word_meta(corpus)
    n_corpus = sum(corpus.values())
    con.sql("CREATE TABLE word_meta (word VARCHAR, zipf DOUBLE, classes VARCHAR, pos VARCHAR, dist DOUBLE)")
    con.executemany("INSERT INTO word_meta VALUES (?, ?, ?, ?, ?)",
                    [(w, *m) for w, m in wmeta.items()])
    con.sql(f"COPY (SELECT * FROM word_meta ORDER BY word) TO '{out / 'word_meta.parquet'}' (FORMAT parquet)")

    def tag(word, value):
        z, c, p, _ = wmeta.get(word, (0.0, "x", "x", 0.0))
        return [word, value, z, c, p]

    movie_cols = ["imdb_id", "title", "year", "total_words", "unique_words",
                  "words_per_minute", "original_language"]
    meta = {row[0]: dict(zip(movie_cols, row)) for row in
            con.sql(f"SELECT {', '.join(movie_cols)} FROM movies").fetchall()}
    for row in con.sql(f"SELECT {', '.join(movie_cols)}, quality, quality_flags "
                       f"FROM flagged").fetchall():
        meta[row[0]] = dict(zip(movie_cols, row)) | {
            "quality": quality_note(row[-2], row[-1])}

    def flush(imdb_id, rows):
        m = meta.get(imdb_id)
        if m is None:
            return
        counts = dict(rows)
        payload = {
            "imdb_id": m["imdb_id"],
            "title": m["title"],
            "year": m["year"],
            "original_language": m["original_language"],
            "stats": {
                "total_words": m["total_words"],
                "unique_words": m["unique_words"],
                "words_per_minute": m["words_per_minute"],
            },
            "top": [tag(wd, c) for wd, c in rows if wd not in stop][:200],
            "top_all": [tag(wd, c) for wd, c in rows][:50],
            "distinctive": [tag(wd, round(z, 2))
                            for wd, z in log_odds(counts, corpus, n_corpus=n_corpus)[:50]],
        }
        if "quality" in m:
            payload["quality"] = m["quality"]
        (out / "json" / "movie" / f"{imdb_id}.json").write_text(
            json.dumps(payload))

    # One streaming pass over the already-sorted (imdb_id, count DESC) parquet
    # instead of one query per movie: at ~30k movies, per-movie queries each
    # re-touch every row group's metadata, which turns O(n) work into hours.
    for parquet in ("words_by_movie", "words_by_movie_flagged"):
        cur = con.execute(
            f"SELECT imdb_id, word, count FROM '{out / parquet / 'data.parquet'}'")
        current, rows = None, []
        while batch := cur.fetchmany(1_000_000):
            for imdb_id, word, count in batch:
                if imdb_id != current:
                    if current is not None:
                        flush(current, rows)
                    current, rows = imdb_id, []
                rows.append((word, count))
        if current is not None:
            flush(current, rows)

    board = con.sql("""
        SELECT word, SUM(count)::BIGINT AS count,
               COUNT(DISTINCT wc.imdb_id) AS movie_count
        FROM wc JOIN movies USING (imdb_id)
        GROUP BY word
        ORDER BY count DESC
    """).fetchall()
    (out / "json" / "leaderboard-default.json").write_text(json.dumps({
        "words": [[wd, c, mc, *wmeta.get(wd, (0.0, "x", "x", 0.0))]
                  for wd, c, mc in board if wd not in stop][:1000],
        "stopwords": [[wd, c, mc, *wmeta.get(wd, (0.0, "x", "x", 0.0))]
                      for wd, c, mc in board if wd in stop][:50],
    }))


def _write_wordlists(out):
    # Published alongside the dataset so the frontend can offer a stopword-hiding
    # toggle and compute swearing counts client-side without shipping its own
    # copies of these lists (which would drift from the pipeline's).
    (out / "json" / "wordlists.json").write_text(json.dumps({
        "stopwords": sorted(load_stopwords()),
        "profanity": sorted(load_profanity()),
    }))


def _write_report(con, out, corpus):
    n = lambda q: con.sql(q).fetchone()[0]
    curated_n = n("SELECT COUNT(*) FROM curated")
    matched_n = n("SELECT COUNT(*) FROM matched")
    counted_n = n("SELECT COUNT(*) FROM stats")
    enriched_n = n("SELECT COUNT(*) FROM tmdb WHERE imdb_id IS NOT NULL")
    final_n = n("SELECT COUNT(*) FROM movies")
    flagged_n = n("SELECT COUNT(*) FROM flagged")
    kind = ("English-original movies" if corpus == "en"
            else "movies, all original languages")
    report = (
        f"# Pipeline report - corpus '{corpus}'\n\n"
        f"- curated (IMDb movies meeting the vote threshold): {curated_n}\n"
        f"- matched (subtitle file found in OpenSubtitles corpus): {matched_n}\n"
        f"- counted (word counts + stats computed): {counted_n}\n"
        f"- enriched (TMDB metadata found): {enriched_n}\n"
        f"- final ({kind} published): {final_n}\n"
        f"- low subtitle quality (film page only, out of every aggregate): {flagged_n}\n\n"
        "## Drop reasons\n\n"
        f"- curated → matched ({curated_n - matched_n} dropped): no usable "
        "subtitle file found in the OpenSubtitles corpus\n"
        f"- matched → counted ({matched_n - counted_n} dropped): subtitle "
        "file failed word counting (unparseable)\n"
        f"- counted → enriched ({counted_n - enriched_n} dropped): no TMDB "
        "match found for the IMDb id\n"
        + (f"- enriched → final ({enriched_n - final_n} dropped): TMDB "
           f"original_language was not '{config.LANG}'\n" if corpus == "en" else "")
    )
    (out / "report.md").write_text(report)
