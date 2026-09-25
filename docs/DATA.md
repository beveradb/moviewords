# Explore the data yourself

Everything on [moviewords.org](https://moviewords.org) is powered
by five Parquet files per corpus on a public bucket - six for the all-films
corpus, which adds `all/word_year_lang.parquet`. They're free to use for
non-commercial projects - download them, or point DuckDB straight at the URLs
and skip the download entirely.

Only derived word counts are published - no subtitle text is redistributed.

## The files

Base URL: `https://data.moviewords.org`

| File | Size | What's in it |
|------|------|--------------|
| [`movies.parquet`](https://data.moviewords.org/movies.parquet) | 0.8 MB | one row per film: title, year, original_language, genres, rating, word totals |
| [`words_by_movie/data.parquet`](https://data.moviewords.org/words_by_movie/data.parquet) | 88 MB | `(imdb_id, word, count)`, sorted by film |
| [`words_by_word/data.parquet`](https://data.moviewords.org/words_by_word/data.parquet) | 93 MB | same rows, sorted by word |
| [`word_year.parquet`](https://data.moviewords.org/word_year.parquet) | 6 MB | `(word, year, count, movie_count)` for trends |
| [`word_meta.parquet`](https://data.moviewords.org/word_meta.parquet) | 3.5 MB | per-word commonness (zipf), part of speech, distinctiveness |

About 0.8% of films (mostly 1930s-60s English-original films whose only
subtitle is machine-translated or auto-captioned) are left out of these files
so their words can't skew the numbers; they're in `movies_flagged.parquet` and
`words_by_movie_flagged/data.parquet` (same schemas, plus `quality` and
`quality_flags`).

The two big files are sorted copies of the same rows: use `words_by_movie` when
you're starting from a film, `words_by_word` when you're starting from a word -
Parquet row-group pruning makes queries against the matching sort order fast
enough to run from a browser.

Full column-by-column schema:
[the dataset contract](ARCHITECTURE.md#the-dataset-contract).

## Two corpora

Every artifact exists twice: at the bucket root for the default corpus
(English-original films) and under the `all/` prefix for the all-films
corpus (translated subtitles included), e.g.
`https://data.moviewords.org/all/movies.parquet`. Both use `numVotes >= 300`.
`movies.parquet` carries `original_language` (ISO 639-1) in both corpora.

The all-films corpus adds `all/word_year_lang.parquet`
`(word, year, lang, count, movie_count)` - per-original-language trend
counts, keeping a (word, lang) pair when its corpus-wide total is >= 20.
Posters are shared at `posters/<imdb_id>.jpg` (plus an `.avif` twin) regardless of corpus.

## Query it without downloading

DuckDB reads Parquet over HTTP and only fetches the row groups it needs:

```bash
# chattiest films
duckdb -c "SELECT title, year, words_per_minute
           FROM 'https://data.moviewords.org/movies.parquet'
           ORDER BY words_per_minute DESC LIMIT 10"

# which films say a word the most
duckdb -c "SELECT m.title, m.year, w.count
           FROM 'https://data.moviewords.org/words_by_word/data.parquet' w
           JOIN 'https://data.moviewords.org/movies.parquet' m USING (imdb_id)
           WHERE w.word = 'sword' ORDER BY w.count DESC LIMIT 15"

# a word's usage over time
duckdb -c "SELECT year, count, movie_count
           FROM 'https://data.moviewords.org/word_year.parquet'
           WHERE word = 'phone' ORDER BY year"
```

The same works from Python (`duckdb` or `pandas.read_parquet` with the URL),
R (`arrow::read_parquet`), or anything else that speaks Parquet + HTTP.

## License and attribution

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) -
non-commercial, attribution, share-alike.

Word counts are derived from the
[OPUS OpenSubtitles corpus](https://opus.nlpl.eu/datasets/OpenSubtitles)
(Lison & Tiedemann, 2016), built from subtitles by
[OpenSubtitles.org](http://www.opensubtitles.org/); film metadata comes from
the IMDb non-commercial datasets and [TMDB](https://www.themoviedb.org).
Please credit those sources too if you republish anything built on this data.

## Built something?

There must be cool analyses this data could power that we haven't thought of.
If you build something - or want to see an analysis added to the site -
[email andrew@beveridge.uk](mailto:andrew@beveridge.uk?subject=Movie%20Words%20idea).
