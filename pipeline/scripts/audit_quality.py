#!/usr/bin/env python
"""Subtitle data-quality audit: the canaries that show a wrong or bad
subtitle reached the site. Run after every `count` (and before publishing),
from data/work - no raw files needed:

  uv run python scripts/audit_quality.py [--out audit.json] [--baseline old.json]

Prints a markdown report; --out saves the findings so the next run can
--baseline against them and show what changed. Canaries (see
docs/handoffs/2026-09-25-subtitle-data-quality.md, #11):

- tiers: films per quality tier / flag, by era and language
- profanity: strong swearing (fuck/cunt/shit families) in English-original
  films before 1968 (the Production Code era - genuine hits are 1960s
  documentaries/underground films and profanity_verified.txt)
- anachronisms: words that can't be said before a year (internet, email...)
- rates: implausible words per minute (non-silent films under 10, over 200)
- silent rates: films from before talkies speaking at talkie rates (a
  silent film's genuine subtitle is its intertitles, ~10-20 words/min)
- grey zone: machine-translation scores just under the flag threshold
- known cases: films whose subtitles went wrong before
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

from moviewords_pipeline import config, quality  # noqa: E402
from moviewords_pipeline.counts import load_profanity_verified  # noqa: E402

PROFANITY_BEFORE = 1968
# Before this year every film is silent (The Jazz Singer, Oct 1927, was a
# part-talkie; 1928 mixes both). Genuine intertitles run 10-20 words/min,
# wordy ones up to ~65 (The Great White Silence, Orochi); wrong films and
# commentary tracks filed under silents ran 59-135.
SILENT_BEFORE = 1928
SILENT_RATE_MAX = 45
# word -> first year it can plausibly be said in a film's dialogue
ANACHRONISMS = {
    "internet": 1993, "email": 1990, "emails": 1990, "website": 1994,
    "cellphone": 1987, "smartphone": 2005, "laptop": 1985, "wifi": 2001,
    "google": 1999, "googled": 2002, "texting": 2000, "texted": 2000,
    "facebook": 2004, "youtube": 2005, "iphone": 2007, "ipod": 2001,
    "selfie": 2010, "dvd": 1996, "online": 1985,
}
KNOWN = {
    "tt0018455": "Sunrise (1927): silent - intertitle files were below the index floor",
    "tt0038680": "Lady Luck (1946): 2 copies of a modern film beat the genuine file",
    "tt0059930": "Young Cassidy (1965): back-translated",
    "tt0022134": "Arizona (1931): auto-captions",
    "tt0045251": "Othello (1951): O (2001) filed under it",
    "tt0107818": "Philadelphia (1993): a Vietnamese file",
    "tt4849438": "Baahubali 2 (2017): 3 copies of another film",
    "tt0113277": "Heat (1995): DVD commentary track",
    "tt0018379": "7th Heaven (1927): silent - only file was a modern gymnastics drama (blocklisted)",
    "tt0019290": "The Power of the Press (1928): the 1943 film beat the intertitles",
    "tt0037166": "Passage to Marseille (1944): \"SHIT.\" transcription slip",
}
GREY_ZONE = (0.4, config.MT_SCORE_MAX)


def connect(work):
    con = duckdb.connect()
    sel = work / "selection.parquet"
    cols = {c for (c,) in con.sql(f"SELECT column_name FROM (DESCRIBE '{sel}')").fetchall()}
    # selections from before quality tiers (SELECTION_VERSION < 3) read as all-ok
    extra = "" if "tier" in cols else ", 'ok' AS tier, '[]' AS flags"
    con.sql(f"""
        CREATE VIEW sel AS SELECT *{extra} FROM '{sel}';
        CREATE VIEW wc AS SELECT * FROM '{work / "word_counts.parquet"}';
        CREATE VIEW stats AS SELECT * FROM '{work / "movie_stats.parquet"}';
        CREATE VIEW curated AS SELECT * FROM '{work / "curated.parquet"}';
        CREATE TABLE tmdb AS SELECT * FROM read_json('{work / "tmdb"}/*.json',
            columns={{'imdb_id': 'VARCHAR', 'original_language': 'VARCHAR'}});
        CREATE TABLE films AS
        SELECT s.imdb_id, c.title, c.year, c.genres, c.runtime_minutes, t.original_language AS lang,
               s.tier, s.flags, s.reason, s.zip_name, st.total_words, st.words_per_minute
        FROM sel s JOIN curated c USING (imdb_id)
        LEFT JOIN tmdb t USING (imdb_id) LEFT JOIN stats st USING (imdb_id);
    """)
    return con


def tiers(con):
    rows = con.sql("""
        SELECT tier, flags, (lang = 'en') AS english,
               CASE WHEN year < 1930 THEN 'pre-1930' WHEN year < 1968 THEN '1930-67'
                    WHEN year < 2000 THEN '1968-99' ELSE '2000+' END AS era,
               COUNT(*) AS n
        FROM films GROUP BY ALL ORDER BY ALL
    """).fetchall()
    return [dict(zip(("tier", "flags", "english", "era", "n"), r)) for r in rows]


def profanity(con):
    """Films saying any word of the fuck/cunt/shit families (the pipeline's
    own quality.STRONG_PROFANITY_RE, so "fuckin'", "shithead" and "shit's"
    count and "shittim" doesn't)."""
    verified = load_profanity_verified()
    films = {}
    for imdb_id, title, year, genres, word, n in con.sql(f"""
        SELECT f.imdb_id, f.title, f.year, f.genres, wc.word, wc.count::INT
        FROM films f JOIN wc USING (imdb_id)
        WHERE f.tier = 'ok' AND f.lang = 'en' AND f.year < {PROFANITY_BEFORE}
          AND (wc.word LIKE '%fuck%' OR wc.word LIKE '%shit%' OR wc.word LIKE 'cunt%')
        ORDER BY f.year, f.imdb_id, wc.count DESC
    """).fetchall():
        if not quality.STRONG_PROFANITY_RE.match(word):
            continue
        r = films.setdefault(imdb_id, {"imdb_id": imdb_id, "title": title, "year": year,
                                       "genres": genres, "hits": 0, "words": [],
                                       "verified": imdb_id in verified})
        r["hits"] += n
        r["words"].append(f"{word} x{n}")
    return list(films.values())


def silent_rates(con):
    return [dict(zip(("imdb_id", "title", "year", "wpm", "total_words"), r)) for r in con.sql(f"""
        SELECT imdb_id, title, year, round(words_per_minute, 1), total_words FROM films
        WHERE tier = 'ok' AND year < {SILENT_BEFORE} AND words_per_minute > {SILENT_RATE_MAX}
        ORDER BY words_per_minute DESC
    """).fetchall()]


def anachronisms(con):
    cases = " OR ".join(f"(wc.word = '{w}' AND f.year < {y})" for w, y in ANACHRONISMS.items())
    return [dict(zip(("imdb_id", "title", "year", "words"), r)) for r in con.sql(f"""
        SELECT f.imdb_id, f.title, f.year,
               string_agg(wc.word || ' x' || wc.count, ', ' ORDER BY wc.count DESC)
        FROM films f JOIN wc USING (imdb_id)
        WHERE f.tier = 'ok' AND ({cases})
        GROUP BY ALL ORDER BY f.year, f.imdb_id
    """).fetchall()]


def rates(con):
    return [dict(zip(("imdb_id", "title", "year", "wpm", "total_words"), r)) for r in con.sql(f"""
        SELECT imdb_id, title, year, round(words_per_minute, 1), total_words FROM films
        WHERE tier = 'ok' AND words_per_minute IS NOT NULL
          AND ((words_per_minute < 10 AND year >= {config.SILENT_ERA_END_YEAR}
                AND NOT list_contains(genres, 'Documentary'))
               OR words_per_minute > {config.MAX_COUNTED_WPM})
        ORDER BY words_per_minute
    """).fetchall()]


def grey_zone(con, cache_dir):
    """Chosen files of English-original films (the style model judges no
    others) scoring just under the machine-translation threshold."""
    out = []
    for imdb_id, title, year, zip_name in con.sql(
            "SELECT imdb_id, title, year, zip_name FROM films WHERE tier = 'ok' AND lang = 'en'").fetchall():
        path = cache_dir / f"{imdb_id}.json"
        if not zip_name or not path.exists():
            continue
        fp = json.loads(path.read_text())["fingerprints"].get(zip_name, {})
        if "q" not in fp:
            continue
        score = quality.mt_score(fp["q"], fp["tokens"])
        if score is not None and GREY_ZONE[0] <= score < GREY_ZONE[1]:
            out.append({"imdb_id": imdb_id, "title": title, "year": year,
                        "mt_score": round(score, 3)})
    return sorted(out, key=lambda r: -r["mt_score"])


def known(con):
    rows = {r[0]: r for r in con.sql(
        "SELECT imdb_id, tier, flags, reason, zip_name FROM films").fetchall()}
    out = []
    for imdb_id, note in KNOWN.items():
        r = rows.get(imdb_id)
        top = [w for (w,) in con.sql(
            f"SELECT word FROM wc WHERE imdb_id = '{imdb_id}' AND length(word) > 3 "
            f"ORDER BY count DESC LIMIT 60").fetchall()]
        from moviewords_pipeline.derive import load_stopwords
        stop = load_stopwords()
        out.append({"imdb_id": imdb_id, "note": note,
                    "tier": r[1] if r else "absent", "flags": r[2] if r else None,
                    "reason": r[3] if r else None, "zip_name": r[4] if r else None,
                    "top_words": [w for w in top if w not in stop][:12]})
    return out


def diff(now, before, key="imdb_id"):
    a = {r[key] for r in before}
    b = {r[key] for r in now}
    return sorted(b - a), sorted(a - b)


def report(findings, baseline=None):
    lines = ["# Subtitle quality audit", ""]
    lines += ["## Tiers", "", "| tier | flags | English-original | era | films |", "|---|---|---|---|---|"]
    lines += [f"| {r['tier']} | {r['flags']} | {r['english']} | {r['era']} | {r['n']:,} |"
              for r in findings["tiers"]]
    sections = [
        ("profanity", f"Strong profanity, English-original, before {PROFANITY_BEFORE} (tier ok)",
         lambda r: f"{r['year']} {r['title']} ({r['imdb_id']}) {', '.join(r['words'])} "
                   f"{r['genres']}{' - verified genuine' if r['verified'] else ''}"),
        ("anachronisms", "Anachronisms (tier ok)",
         lambda r: f"{r['year']} {r['title']} ({r['imdb_id']}): {r['words']}"),
        ("rates", "Implausible words per minute (tier ok)",
         lambda r: f"{r['wpm']} wpm - {r['year']} {r['title']} ({r['imdb_id']}), {r['total_words']} words"),
        ("silent_rates", f"Silent era (before {SILENT_BEFORE}) at talkie rates, over {SILENT_RATE_MAX} words/min (tier ok)",
         lambda r: f"{r['wpm']} wpm - {r['year']} {r['title']} ({r['imdb_id']}), {r['total_words']} words"),
        ("grey_zone", f"Machine-translation grey zone {GREY_ZONE} (tier ok)",
         lambda r: f"{r['mt_score']} - {r['year']} {r['title']} ({r['imdb_id']})"),
    ]
    for key, title, fmt in sections:
        rows = findings[key]
        lines += ["", f"## {title}: {len(rows)}", ""]
        if baseline and key in baseline:
            new, gone = diff(rows, baseline[key])
            lines += [f"vs baseline: +{len(new)} new, -{len(gone)} gone"
                      + (f" (new: {', '.join(new[:20])})" if new else ""), ""]
        lines += [f"- {fmt(r)}" for r in rows[:200]]
        if len(rows) > 200:
            lines.append(f"- ... {len(rows) - 200} more (see --out)")
    lines += ["", "## Known cases", ""]
    for r in findings["known"]:
        lines.append(f"- **{r['note']}** - tier {r['tier']} {r['flags'] or ''} "
                     f"({r['reason']}): {' '.join(r['top_words'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=config.WORK_DIR)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--baseline", type=Path)
    args = ap.parse_args()
    con = connect(args.work)
    findings = {"tiers": tiers(con), "profanity": profanity(con),
                "anachronisms": anachronisms(con), "rates": rates(con),
                "silent_rates": silent_rates(con),
                "grey_zone": grey_zone(con, args.work / "counts" / config.LANG),
                "known": known(con)}
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    print(report(findings, baseline))
    if args.out:
        args.out.write_text(json.dumps(findings, indent=1, default=str))


if __name__ == "__main__":
    main()
