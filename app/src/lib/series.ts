import { fetchJSON, globalUrl, langUrl } from './data'
import { langFilterSql, lit, pq, q } from './duck'
import { activeLanguages } from './languages'
import { mergeTopFilms, mergeTrendLines, mergeYearTotals } from './merge'
import {
  groupTopMovies,
  toSeries,
  trendByYear,
  trendTopFilms,
  trendYearRows,
  wordKey,
  type TopFilm,
  type TrendFile,
  type WordSeries,
  type YearRow,
  type YearTopMovie,
} from './trends'

let yearTotalsCache: Map<number, number> | null = null

/** Whole-corpus word total per release year, cached for the session. */
export async function yearTotals(): Promise<Map<number, number>> {
  if (yearTotalsCache) return yearTotalsCache
  const rows = await q<{ year: number; total: number }>(
    `SELECT year, SUM(count)::DOUBLE AS total FROM ${pq('word_year.parquet')} GROUP BY year`,
  )
  yearTotalsCache = new Map(rows.map((r) => [r.year, r.total]))
  return yearTotalsCache
}

/** Language-scoped word total per release year: word_year.parquet is a single
 * global pre-aggregation with no per-language breakdown, so a language-scoped
 * rate needs its own denominator - sum every film's word count via
 * `words_by_movie` (unfiltered per-word rows, unlike the floored word_year
 * table) joined to `movies` for the language filter. Not cached across
 * language selections; callers already scope each call to the active filter
 * and this is a rare (engine-fallback) path. */
async function yearTotalsForLangs(filter: string): Promise<Map<number, number>> {
  const rows = await q<{ year: number; total: number }>(
    `SELECT m.year AS year, SUM(w.count)::DOUBLE AS total
     FROM ${pq('words_by_movie/data.parquet')} w
     JOIN ${pq('movies.parquet')} m USING (imdb_id)
     WHERE 1=1${filter}
     GROUP BY m.year`,
  )
  return new Map(rows.map((r) => [r.year, r.total]))
}

/** Load per-year usage rates for the given words and shape them into chart
 * series. 0 languages -> word_year.parquet only (small, no top-movie join),
 * same as today. 1+ -> language-scoped: join movies for the language filter,
 * so this pays for words_by_word instead of the pre-aggregated table - and the
 * denominator is language-scoped too (yearTotalsForLangs), otherwise the rate
 * would divide a filtered numerator by the unfiltered whole-corpus total. */
export async function loadWordSeries(words: string[], colors: string[]): Promise<WordSeries> {
  const inList = words.map(lit).join(',')
  const filter = langFilterSql('m')
  const sql = filter
    ? `SELECT w.word, m.year, SUM(w.count)::DOUBLE AS count
       FROM ${pq('words_by_word/data.parquet')} w
       JOIN ${pq('movies.parquet')} m USING (imdb_id)
       WHERE w.word IN (${inList})${filter}
       GROUP BY w.word, m.year ORDER BY w.word, m.year`
    : `SELECT word, year, count::DOUBLE AS count FROM ${pq('word_year.parquet')}
       WHERE word IN (${inList}) ORDER BY word, year`
  const [rows, totals] = await Promise.all([
    q<YearRow>(sql),
    filter ? yearTotalsForLangs(filter) : yearTotals(),
  ])
  return toSeries(rows, totals, words, colors)
}

interface FeaturedSeriesFile {
  totals: Record<string, number>
  words: Record<string, [number, number][]>
}

/** Fetch one language's featured-series.json; throws on any non-OK status
 * (no 404-as-empty here - unlike per-word trend files, this aggregate is
 * expected to exist for every language in the manifest). */
async function fetchFeaturedFile(code: string): Promise<FeaturedSeriesFile> {
  const res = await fetch(langUrl(code, 'json/featured-series.json'))
  if (!res.ok) throw new Error(`${res.status} fetching featured-series [${code}]`)
  return res.json() as Promise<FeaturedSeriesFile>
}

/** Merge per-language featured-series files: totals summed per year (exact),
 * each word's [year,count] line summed via mergeTrendLines. A word absent
 * from one language's file just contributes nothing for that language. */
function mergeFeaturedFiles(parts: FeaturedSeriesFile[]): FeaturedSeriesFile {
  const totalsMaps = parts.map((p) => new Map(Object.entries(p.totals).map(([y, t]) => [Number(y), t])))
  const totals = Object.fromEntries(
    [...mergeYearTotals(totalsMaps)].map(([y, t]) => [String(y), t]),
  )
  const words: Record<string, [number, number][]> = {}
  for (const w of new Set(parts.flatMap((p) => Object.keys(p.words)))) {
    words[w] = mergeTrendLines(parts.map((p) => p.words[w] ?? []))
  }
  return { totals, words }
}

/** Featured-chart data from the pre-baked JSON (a few KB), so the homepage
 * never pays for the SQL engine. Any word missing from the bake (stale file,
 * fetch failure) falls back to the live DuckDB path. 0 languages -> the global
 * file as today; 1+ -> fetch+merge the selected languages' files. */
export async function loadFeaturedSeries(words: string[], colors: string[]): Promise<WordSeries> {
  try {
    const langs = activeLanguages()
    const baked = langs.length
      ? mergeFeaturedFiles(await Promise.all(langs.map(fetchFeaturedFile)))
      : await fetchJSON<FeaturedSeriesFile>('json/featured-series.json')
    if (words.every((w) => baked.words[w])) {
      const totals = new Map(Object.entries(baked.totals).map(([y, t]) => [Number(y), t]))
      const rows: YearRow[] = words.flatMap((w) =>
        baked.words[w].map(([year, count]) => ({ word: w, year, count })),
      )
      return toSeries(rows, totals, words, colors)
    }
  } catch {
    // fall through to the engine
  }
  // visible breadcrumb: this fallback quietly costs the visitor the whole
  // engine download, so a stale/missing bake should never go unnoticed
  console.warn(`featured-series.json bake missing [${words.join(', ')}] - falling back to the SQL engine`)
  return loadWordSeries(words, colors)
}

/** Everything the Trends view needs for a set of words: the chart series, the
 * "films that say it most" table, and the top-movie-per-year notes/table. */
export interface TrendsData {
  wordSeries: WordSeries
  topFilms: Map<string, TopFilm[]>
  topMovies: Map<string, Map<number, YearTopMovie>>
  /** false when we fell back to the live SQL engine (stale/missing bake). */
  baked: boolean
}

// keyed by file + selected languages so a filter change never serves a stale map
const yearMapCache = new Map<string, Promise<Map<number, number>>>()

const toYearMap = (obj: Record<string, number>) =>
  new Map(Object.entries(obj).map(([y, t]) => [Number(y), t]))

/** A pre-baked per-year number map (a couple of KB), cached for the session.
 * 0 languages -> the global file; 1+ -> fetch + sum the selected languages'
 * files. year-totals.json = words per year (rate denominator); year-films.json
 * = films per year (per-film denominator). */
function bakedYearMap(file: 'year-totals.json' | 'year-films.json'): Promise<Map<number, number>> {
  const langs = activeLanguages()
  const key = `${file}|${langs.join(',')}`
  const hit = yearMapCache.get(key)
  if (hit) return hit
  const p = (async () => {
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

const bakedYearTotals = () => bakedYearMap('year-totals.json')

/** Films released per year (language-aware) - the Trends per-film denominator. */
export const bakedYearFilms = () => bakedYearMap('year-films.json')

/** Merge per-language TrendFiles: line summed exactly, top/byYear unioned and
 * re-ranked. */
export function mergeTrendFiles(parts: TrendFile[]): TrendFile {
  const top = mergeTopFilms(
    [parts.flatMap((p) => p.top).map((t) => ({ t, count: t[3] }))], 15,
  ).map((x) => x.t)
  const byYear = new Map<number, TrendFile['byYear'][number]>()
  for (const p of parts) for (const r of p.byYear) {
    const cur = byYear.get(r[0])
    if (!cur || r[3] > cur[3]) byYear.set(r[0], r)
  }
  return {
    line: mergeTrendLines(parts.map((p) => p.line)),
    top,
    byYear: [...byYear.values()].sort((a, b) => a[0] - b[0]),
  }
}

/** A single word's baked trend file, or null when no selected language has
 * data for it (the word isn't in the baked corpus, i.e. below the eligibility
 * threshold = "not enough data"). 0 languages -> the global file, same 404
 * contract as before. 1+ -> fetch each selected language's file; a 404 there
 * contributes nothing, and only if ALL of them 404 do we return null -
 * otherwise the non-404 parts are merged. Any other failure throws so
 * `loadTrends` can fall back to the live engine. */
async function fetchTrendFile(word: string): Promise<TrendFile | null> {
  const key = wordKey(word)
  const langs = activeLanguages()
  if (!langs.length) {
    const res = await fetch(globalUrl(`json/trend/${key}.json`))
    if (res.status === 404) return null
    if (!res.ok) throw new Error(`${res.status} fetching trend/${word}`)
    return res.json() as Promise<TrendFile>
  }
  const parts = await Promise.all(
    langs.map(async (code) => {
      const res = await fetch(langUrl(code, `json/trend/${key}.json`))
      if (res.status === 404) return null
      if (!res.ok) throw new Error(`${res.status} fetching trend/${word} [${code}]`)
      return res.json() as Promise<TrendFile>
    }),
  )
  const present = parts.filter((p): p is TrendFile => p !== null)
  if (!present.length) return null
  return mergeTrendFiles(present)
}

/** Trends data from the pre-baked per-word JSON - no SQL engine, so mobile
 * never pays the ~35 MB DuckDB-WASM cold-boot. A word with no data for any
 * selected language is treated as "not enough data" (it drops through
 * `toSeries`'s missing list); any other failure degrades to the live engine,
 * same contract as loadFeaturedSeries. */
export async function loadTrends(words: string[], colors: string[]): Promise<TrendsData> {
  try {
    const [totals, files] = await Promise.all([
      bakedYearTotals(),
      Promise.all(words.map(fetchTrendFile)),
    ])
    const rows = words.flatMap((w, i) => (files[i] ? trendYearRows(w, files[i] as TrendFile) : []))
    const wordSeries = toSeries(rows, totals, words, colors)
    // every requested word gets a topFilms entry (empty for 404/no-data words)
    // so `topFilms.get(word)` never returns undefined - a null there means the
    // whole batch is still loading and would spin the table forever
    const topFilms = new Map<string, TopFilm[]>()
    const topMovies = new Map<string, Map<number, YearTopMovie>>()
    words.forEach((w, i) => {
      const f = files[i]
      topFilms.set(w, f ? trendTopFilms(f) : [])
      if (f) topMovies.set(w, trendByYear(f))
    })
    return { wordSeries, topFilms, topMovies, baked: true }
  } catch (e) {
    console.warn(`trend bake unavailable [${words.join(', ')}] - falling back to the SQL engine`, e)
    return loadTrendsEngine(words, colors)
  }
}

/** Live-engine fallback: the pre-bake queries this replaced, kept working so a
 * stale/missing bake still renders (at the cost of the engine download). Also
 * language-scoped via `langFilterSql`, so a bake miss while a language filter
 * is active doesn't silently show the whole corpus. */
async function loadTrendsEngine(words: string[], colors: string[]): Promise<TrendsData> {
  const inList = words.map(lit).join(',')
  const filter = langFilterSql('m')
  const [wordSeries, filmRows, movieRows] = await Promise.all([
    loadWordSeries(words, colors),
    q<TopFilm & { word: string }>(
      `SELECT w.word, w.imdb_id, m.title, m.year, w.count::DOUBLE AS count, m.total_words::DOUBLE AS total_words
       FROM ${pq('words_by_word/data.parquet')} w
       JOIN ${pq('movies.parquet')} m USING (imdb_id)
       WHERE w.word IN (${inList})${filter}
       QUALIFY ROW_NUMBER() OVER (PARTITION BY w.word ORDER BY w.count DESC, m.title) <= 15
       ORDER BY w.word, count DESC, m.title`,
    ),
    q<YearTopMovie & { word: string; year: number }>(
      `SELECT word, year, imdb_id, title, count FROM (
         SELECT w.word, m.year, w.imdb_id, m.title, w.count::DOUBLE AS count,
                ROW_NUMBER() OVER (PARTITION BY w.word, m.year ORDER BY w.count DESC, m.title) AS rn
         FROM ${pq('words_by_word/data.parquet')} w
         JOIN ${pq('movies.parquet')} m USING (imdb_id)
         WHERE w.word IN (${inList})${filter}
       ) WHERE rn = 1`,
    ),
  ])
  // seed every word with [] so a word with zero film rows renders nothing
  // rather than a permanent spinner (matches the pre-refactor per-word query)
  const topFilms = new Map<string, TopFilm[]>(words.map((w) => [w, []]))
  for (const r of filmRows) {
    topFilms.get(r.word)?.push({
      imdb_id: r.imdb_id,
      title: r.title,
      year: r.year,
      count: r.count,
      total_words: r.total_words,
    })
  }
  return { wordSeries, topFilms, topMovies: groupTopMovies(movieRows), baked: false }
}
