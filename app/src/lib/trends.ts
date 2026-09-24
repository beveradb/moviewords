import type { Series } from '../components/LineChart'

/** Pure logic for the trends view, split out so it's testable without
 * dragging in duckdb-wasm. */

/** Years whose whole corpus has fewer dialogue words than this are hidden from
 * trend charts. Below ~100k words a single film mentioning a word once moves
 * its rate by 10+ per million, so thin years chart as huge fake spikes. That's
 * the pre-1930 silent era (1-16 films each, and intertitles are ~10x shorter
 * than talkie scripts) and the trailing years still being ingested (2-3 films
 * each). Every kept year has 18+ films. */
export const MIN_YEAR_WORDS = 100_000

export interface YearTopMovie {
  imdb_id: string
  title: string
  count: number
}

/** Flat top-movie-per-year query rows → word → year → that year's top movie. */
export const groupTopMovies = (
  rows: (YearTopMovie & { word: string; year: number })[],
): Map<string, Map<number, YearTopMovie>> => {
  const byWord = new Map<string, Map<number, YearTopMovie>>()
  for (const { word, year, imdb_id, title, count } of rows) {
    if (!byWord.has(word)) byWord.set(word, new Map())
    byWord.get(word)!.set(year, { imdb_id, title, count })
  }
  return byWord
}

/** One row per plotted year, ascending; movie is null where the word never
 * occurs so the year sequence stays unbroken. */
export const topMovieRows = (years: number[], byYear: Map<number, YearTopMovie> | undefined) =>
  [...years].sort((a, b) => a - b).map((year) => ({ year, movie: byYear?.get(year) ?? null }))

/** Click-to-pin on the trend chart: toggle a year in the pinned list,
 * dropping the oldest pin beyond `max` so exploring never needs a manual
 * unpin first. */
export const togglePin = (pins: number[], x: number, max = 3) =>
  pins.includes(x) ? pins.filter((v) => v !== x) : [...pins, x].slice(-max)

/** "1916–1929, 2024" from a sorted list of years */
export const formatYearRanges = (years: number[]) =>
  years
    .reduce<[number, number][]>((acc, y) => {
      const last = acc[acc.length - 1]
      if (last && y === last[1] + 1) last[1] = y
      else acc.push([y, y])
      return acc
    }, [])
    .map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`))
    .join(', ')

export interface YearRow {
  word: string
  year: number
  count: number
}

/** A word → filename/URL key for the pre-baked `json/trend/<key>.json` files.
 * MUST stay byte-for-byte identical to the pipeline's Python `quote(w, safe="")`
 * (RFC3986: only `A-Z a-z 0-9 - _ . ~` stay literal). `encodeURIComponent`
 * leaves `! ' ( ) *` unescaped, so we percent-encode those too - otherwise
 * words like `don't` would resolve to the wrong key and 404. */
export const wordKey = (word: string): string =>
  encodeURIComponent(word).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`)

/** Shape of a pre-baked per-word trend file. Compact arrays keep files tiny;
 * field order is a contract with the pipeline bake (see the handoff spec). */
export interface TrendFile {
  /** [year, count] for this word, ascending by year. */
  line: [number, number][]
  /** up to 15 [imdb_id, title, year, count, total_words], count DESC. */
  top: [string, string, number, number, number][]
  /** [year, imdb_id, title, count] - the single top film per year. */
  byYear: [number, string, string, number][]
}

export interface TopFilm {
  imdb_id: string
  title: string
  year: number
  count: number
  total_words: number
}

/** Baked line → the flat YearRow shape `toSeries` consumes. */
export const trendYearRows = (word: string, file: TrendFile): YearRow[] =>
  file.line.map(([year, count]) => ({ word, year, count }))

/** Baked top array → the objects the Films-that-say-it-most table renders. */
export const trendTopFilms = (file: TrendFile): TopFilm[] =>
  file.top.map(([imdb_id, title, year, count, total_words]) => ({ imdb_id, title, year, count, total_words }))

/** Baked byYear array → the year→top-movie map the by-year table renders. */
export const trendByYear = (file: TrendFile): Map<number, YearTopMovie> =>
  new Map(file.byYear.map(([year, imdb_id, title, count]) => [year, { imdb_id, title, count }]))

export interface WordSeries {
  series: Series[]
  plottedYears: number[]
  trimmedYears: string | null
  missing: string[]
  /** The kept (non-trimmed) raw rows + the denominator used, so a view can
   * re-divide (e.g. per film) without refetching. */
  rows: YearRow[]
  totals: Map<number, number>
}

/** Shape raw word_year rows into chart series (uses per million words of
 * dialogue), plus the plotted-year list, trimmed-year note, and missing words.
 * Years whose whole-corpus word total is below MIN_YEAR_WORDS are dropped as
 * too sparse for a reliable rate. Colors are assigned by drawn-series order. */
export function toSeries(
  rows: YearRow[],
  totals: Map<number, number>,
  words: string[],
  colors: string[],
): WordSeries {
  const kept = rows.filter((r) => (totals.get(r.year) ?? 0) >= MIN_YEAR_WORDS)
  const droppedYears = [
    ...new Set(rows.filter((r) => (totals.get(r.year) ?? 0) < MIN_YEAR_WORDS).map((r) => r.year)),
  ].sort((a, b) => a - b)
  const trimmedYears = droppedYears.length ? formatYearRanges(droppedYears) : null

  const byWord = new Map<string, YearRow[]>()
  kept.forEach((r) => byWord.set(r.word, [...(byWord.get(r.word) ?? []), r]))
  const missing = words.filter((w) => !byWord.has(w))

  const keptYears = kept.map((r) => r.year)
  const plottedYears = keptYears.length
    ? [...totals.entries()]
        .filter(([y, t]) => t >= MIN_YEAR_WORDS && y >= Math.min(...keptYears) && y <= Math.max(...keptYears))
        .map(([y]) => y)
        .sort((a, b) => a - b)
    : []

  const series = words
    .filter((w) => byWord.has(w))
    .map((w, i) => ({
      name: w,
      color: colors[i],
      points: byWord.get(w)!.map((r) => ({ x: r.year, y: (r.count / (totals.get(r.year) ?? 1)) * 1_000_000 })),
    }))

  return { series, plottedYears, trimmedYears, missing, rows: kept, totals }
}

/** Re-divide a word series' yearly counts by films released that year
 * (average uses per film). Years without a film count are dropped. */
export function perFilmSeries(ws: WordSeries, films: Map<number, number>): Series[] {
  const counts = new Map(ws.rows.map((r) => [`${r.word}|${r.year}`, r.count]))
  return ws.series.map((s) => ({
    ...s,
    points: s.points.flatMap((p) => {
      const f = films.get(p.x)
      const c = counts.get(`${s.name}|${p.x}`)
      return f && c !== undefined ? [{ ...p, y: c / f }] : []
    }),
  }))
}

/** "N uses per film in the <decade>s (all years: M)": pooled averages over the
 * plotted years (a plotted year the word is absent from counts as 0 uses). */
export function perFilmSummary(
  ws: WordSeries,
  films: Map<number, number>,
  word: string,
): { decade: number; latest: number; overall: number } | null {
  const counts = new Map(ws.rows.filter((r) => r.word === word).map((r) => [r.year, r.count]))
  if (!counts.size || !ws.plottedYears.length) return null
  const decade = Math.floor(ws.plottedYears[ws.plottedYears.length - 1] / 10) * 10
  const avg = (years: number[]) => {
    let c = 0
    let f = 0
    for (const y of years) {
      c += counts.get(y) ?? 0
      f += films.get(y) ?? 0
    }
    return f ? c / f : 0
  }
  return {
    decade,
    latest: avg(ws.plottedYears.filter((y) => y >= decade)),
    overall: avg(ws.plottedYears),
  }
}

/** Trends URL for a word list; `per=film` only when the per-film view is on,
 * so default links stay unchanged. */
export const trendsHref = (words: string[], perFilm: boolean): string =>
  `/trends?w=${encodeURIComponent(words.join(','))}${perFilm ? '&per=film' : ''}`

export const isPerFilm = (params: URLSearchParams): boolean => params.get('per') === 'film'

/** Per-film averages are often < 1: 1 decimal from 1 up, 2 below, "<0.01"
 * for tiny non-zero values. `n` is the i18n number formatter. */
export function formatPerFilm(v: number, n: (v: number, o?: Intl.NumberFormatOptions) => string): string {
  if (v === 0) return n(0)
  if (v < 0.01) return `<${n(0.01, { minimumFractionDigits: 2 })}`
  const d = v >= 1 ? 1 : 2
  return n(v, { minimumFractionDigits: d, maximumFractionDigits: d })
}
