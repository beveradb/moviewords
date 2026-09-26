# Movie Words - moviewords

**Live: https://moviewords.org** — explore the words spoken in
**two corpora: 34,556 English-original films (default) and 64,046 films of
every original language** (translated subtitles, clearly labeled): what any
movie actually says, how words rise and fall across decades, and what makes a
film, a decade, or a genre sound like itself.

Every film's dialogue (from the [OPUS OpenSubtitles corpus](https://opus.nlpl.eu/datasets/OpenSubtitles),
subtitles by [OpenSubtitles.org](http://www.opensubtitles.org/)) is reduced to a
bag of words and compared against the whole corpus with log-odds — which is how
you learn that *The Godfather Part II*'s signature words are "corleone, fredo,
roth, michael, vito", Horror's are "help, god, please, her, house", and the film
that says "dude" the most is, of course, *The Big Lebowski* (120×).

**Only derived word counts are published — no subtitle text is redistributed.**

## What's here

| Path | What it is |
|---|---|
| `pipeline/` | Python batch pipeline: OPUS + IMDb + TMDB → the published dataset. Runbook in [`pipeline/README.md`](pipeline/README.md) |
| `app/` | The website: Vite + React + Tailwind + DuckDB-WASM, hosted on Cloudflare Pages. Dev guide in [`app/README.md`](app/README.md) |
| `docs/ARCHITECTURE.md` | **Start here to understand or reproduce the system** — architecture, methodology, dataset contract, decisions, toolchain |
| `docs/FAQ.md` | **Methodology, limitations, and licensing questions** — subtitles vs scripts, corpus bias, copyright position, poster policy |
| `docs/DATA-QUALITY.md` | **How bad subtitle files were found and handled** — wrong films, commentary tracks, machine-translated and auto-captioned subtitles, and why old films "said" words they never said |
| `docs/superpowers/` | Original design spec and implementation plan |
| `docs/sessions/` | Session records (how this was actually built, with gotchas) |

## Architecture in one paragraph

A batch pipeline (Python/DuckDB, fully resumable via per-movie caches) turns the
34GB OPUS corpus into ~2GB of Parquet + JSON + posters on a public Cloudflare R2
bucket. The site is a static SPA on Cloudflare Pages that reads pre-baked JSON
for hot paths and runs real SQL in the browser (DuckDB-WASM over HTTP range
requests) for everything interactive. There are no servers and hosting is free.
Details, decisions, and performance lessons: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Reproducing from scratch

1. **Build the dataset** — [`pipeline/README.md`](pipeline/README.md). Needs
   ~60GB disk, a free [TMDB API key](https://www.themoviedb.org/settings/api)
   (`TMDB_API_KEY` or `TMDB_API_TOKEN`), and a few hours (we used a throwaway
   GCP e2-highmem-4; a laptop works too). A 610-film starter dataset needing
   neither is one command: `uv run python scripts/build_demo_dataset.py`.
2. **Host the data** — any static host with range-request + CORS support; we
   use an R2 public bucket (`pipeline/scripts/upload_r2.sh`).
3. **Run the app** — `cd app && npm install && npm run dev`, pointing
   `VITE_DATA_BASE` at your data host. Deploy anywhere static
   (`wrangler pages deploy dist --project-name moviewords`).

## Download the data

The full published dataset is five Parquet files per corpus on a public bucket
(the all-films corpus under `all/` adds a sixth, `word_year_lang.parquet`) —
download them, or point DuckDB straight at the URLs. Fuller guide with more
example queries: [docs/DATA.md](docs/DATA.md).

| File | Size | Contents |
|---|---|---|
| [movies.parquet](https://data.moviewords.org/movies.parquet) | 0.8 MB | one row per film: title, year, genres, rating, word totals |
| [words_by_movie/data.parquet](https://data.moviewords.org/words_by_movie/data.parquet) | 88 MB | (imdb_id, word, count), sorted by film |
| [words_by_word/data.parquet](https://data.moviewords.org/words_by_word/data.parquet) | 93 MB | same rows, sorted by word |
| [word_year.parquet](https://data.moviewords.org/word_year.parquet) | 6 MB | (word, year, count, movie_count) for trends |
| [word_meta.parquet](https://data.moviewords.org/word_meta.parquet) | 3.5 MB | per-word commonness (zipf), part of speech, distinctiveness |

```sh
duckdb -c "SELECT title, year, words_per_minute FROM 'https://data.moviewords.org/movies.parquet' ORDER BY words_per_minute DESC LIMIT 10"
```

Full schema: [the dataset contract](docs/ARCHITECTURE.md#the-dataset-contract).
Got an analysis idea we haven't thought of? Email
[andrew@beveridge.uk](mailto:andrew@beveridge.uk).

## Data & licensing

Code: MIT ([LICENSE](LICENSE)). Published dataset: derived word counts,
CC BY-NC-SA 4.0 ([LICENSE-DATA.md](LICENSE-DATA.md) explains why - IMDb's
non-commercial dataset terms set the floor). Built from: OPUS OpenSubtitles
v2024 (Lison & Tiedemann, 2016) with subtitles from OpenSubtitles.org;
IMDb non-commercial datasets (information courtesy of IMDb, used with
permission); TMDB (metadata & posters — this product uses the TMDB API but
is not endorsed or certified by TMDB). Non-commercial project.

Questions about copyright, methodology, or bias - see the
[FAQ](docs/FAQ.md). Rights holders: takedown requests to
[andrew@beveridge.uk](mailto:andrew@beveridge.uk) are honored promptly.
