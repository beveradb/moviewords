import { useEffect, useMemo, useState } from 'react'
import { getFilteredMovieIndex, getShifts, type Shifts } from '../lib/data'
import { activeLanguages, languageName } from '../lib/languages'
import { navigate, useRoute } from '../lib/route'
import {
  formatPerFilm,
  isPerFilm,
  perFilmSeries,
  perFilmSummary,
  trendsHref,
  type TopFilm,
  type WordSeries,
  type YearTopMovie,
  topMovieRows,
} from '../lib/trends'
import { FEATURED, dayIndex, stepFeatured } from '../lib/featured'
import { bakedYearFilms, loadFeaturedSeries, loadTrends } from '../lib/series'
import { LineChart, type Series } from '../components/LineChart'
import { ErrorBox, FeaturedNav, SeriesLegend, Spinner } from '../components/ui'
import { ExplainerLink } from '../components/FilterExplainer'
import { useI18n } from '../i18n'

const COLORS = ['var(--color-s1)', 'var(--color-s2)', 'var(--color-s3)', 'var(--color-s4)']
const MAX_WORDS = 4

/** Riser/faller chips under the featured chart - one tap to chart a mover. */
function ShiftStrip() {
  const { t } = useI18n()
  const [shifts, setShifts] = useState<Shifts | null>(null)
  useEffect(() => {
    getShifts().then(setShifts).catch(() => {})
  }, [])
  if (!shifts) return null
  const chip = (w: string, dir: '↑' | '↓') => (
    <button
      key={w}
      onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}
      className="border-2 border-ink bg-card px-2 py-0.5 hover:bg-mark"
    >
      {dir} {w}
    </button>
  )
  return (
    <div className="mt-6 font-script text-sm text-ink-2">
      <p className="text-xs uppercase tracking-wide">{t('trends.bigMovers')}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {shifts.risers.slice(0, 6).map((r) => chip(r.word, '↑'))}
        {shifts.fallers.slice(0, 6).map((r) => chip(r.word, '↓'))}
        <a href="#/leaderboard?b=shifts" className="ms-1 underline hover:bg-mark">
          {t('trends.fullList')}
        </a>
      </div>
    </div>
  )
}

/** Answers "which movie says this word the most?" - fed by the pre-baked
 * per-word data (null while the trend fetch is still in flight). */
function TopFilms({ word, rows }: { word: string; rows: TopFilm[] | null }) {
  const { t, n } = useI18n()
  if (rows === null) return <Spinner label={t('trends.topFilmsLoading', { word })} />
  if (rows.length === 0) return null
  const max = rows[0].count
  return (
    <div className="mt-6 border-2 border-ink bg-card p-4">
      <h2 className="slug text-sm">{t('trends.topFilmsHeading', { word })}</h2>
      <ol className="mt-3">
        {rows.map((r, i) => (
          <li key={r.imdb_id} className="flex items-center gap-3 py-1">
            <span className="w-6 text-end font-script text-xs text-ink-3">{i + 1}</span>
            <a
              href={`#/movie/${r.imdb_id}`}
              className="w-56 shrink-0 truncate font-script hover:bg-mark sm:w-72"
            >
              {r.title} <span className="text-xs text-ink-2">({r.year})</span>
            </a>
            <div className="h-4 min-w-1 rounded-e-[4px] bg-s1" style={{ width: `${(r.count / max) * 60}%` }} />
            <span className="shrink-0 font-script text-xs tabular-nums text-ink-2">
              {n(r.count)}×
              <span className="hidden text-ink-3 sm:inline">
                {t('trends.perThousandWords', {
                  rate: n((r.count / r.total_words) * 1000, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
                })}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** All plotted years for the active word, each with its top word-using film. */
function TopFilmsByYear({
  word,
  years,
  byYear,
}: {
  word: string
  years: number[]
  byYear: Map<number, YearTopMovie> | undefined
}) {
  const { t, n } = useI18n()
  const rows = topMovieRows(years, byYear)
  if (rows.length === 0) return null
  return (
    <div className="mt-6 border-2 border-ink bg-card p-4">
      <h2 className="slug text-sm">{t('trends.topFilmByYearHeading', { word })}</h2>
      <div className="mt-3 grid grid-cols-1 gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(({ year, movie }) => (
          <div key={year} className="flex items-baseline gap-2 py-0.5 font-script text-sm">
            <span className="shrink-0 tabular-nums text-xs text-ink-2">{year}</span>
            {movie ? (
              <>
                <a href={`#/movie/${movie.imdb_id}`} className="min-w-0 truncate hover:bg-mark">
                  {movie.title}
                </a>
                <span className="ms-auto shrink-0 text-xs tabular-nums text-ink-3">
                  {n(movie.count)}×
                </span>
              </>
            ) : (
              <span className="text-ink-3">—</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Tabbed per-word detail tables; tabs only appear with 2+ words. */
function WordDetails({
  words,
  years,
  topMovies,
  topFilms,
}: {
  words: string[]
  years: number[]
  topMovies: Map<string, Map<number, YearTopMovie>> | null
  topFilms: Map<string, TopFilm[]> | null
}) {
  const { t } = useI18n()
  const [active, setActive] = useState(0)
  const word = words[Math.min(active, words.length - 1)]
  return (
    <div>
      {words.length > 1 && (
        <div className="mt-6 flex flex-wrap gap-2" role="tablist" aria-label={t('trends.wordDetailsTablist')}>
          {words.map((w, i) => (
            <button
              key={w}
              role="tab"
              aria-selected={w === word}
              onClick={() => setActive(i)}
              className={`flex items-center gap-1.5 border-2 border-ink px-2.5 py-1 font-script text-sm ${
                w === word ? 'bg-mark font-bold' : 'bg-card hover:bg-paper-2'
              }`}
            >
              <span className="inline-block size-2.5 rounded-full" style={{ background: COLORS[i] }} />
              {w}
            </button>
          ))}
        </div>
      )}
      <TopFilms word={word} rows={topFilms?.get(word) ?? null} />
      {topMovies === null ? (
        <Spinner label={t('trends.topFilmByYearLoading', { word })} />
      ) : (
        <TopFilmsByYear word={word} years={years} byYear={topMovies.get(word)} />
      )}
    </div>
  )
}

export function TrendsView() {
  const { t, n, locale } = useI18n()
  const { params } = useRoute()
  const words = useMemo(
    () => (params.get('w') ?? '').split(',').map((w) => w.trim().toLowerCase()).filter(Boolean).slice(0, MAX_WORDS),
    [params],
  )
  const langs = activeLanguages()
  const langLabel = useMemo(() => langs.map((c) => languageName(c, locale)).join(', '), [langs, locale])
  const perFilm = isPerFilm(params)
  const [wordSeries, setWordSeries] = useState<WordSeries | null>(null)
  const [films, setFilms] = useState<Map<number, number> | null>(null)
  const [filmsError, setFilmsError] = useState<string | null>(null)

  useEffect(() => {
    bakedYearFilms().then(setFilms).catch((e) => setFilmsError(String(e)))
  }, [])

  const [input, setInput] = useState('')
  const [filmCount, setFilmCount] = useState<number | null>(null)
  const [series, setSeries] = useState<Series[] | null>(null)
  // per-word top-movie notes + films tables; null while the trend fetch runs
  const [topMovies, setTopMovies] = useState<Map<string, Map<number, YearTopMovie>> | null>(null)
  const [topFilms, setTopFilms] = useState<Map<string, TopFilm[]> | null>(null)
  const [plottedYears, setPlottedYears] = useState<number[]>([])
  const [missing, setMissing] = useState<string[]>([])
  const [trimmedYears, setTrimmedYears] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // no words in the URL → chart a featured shift instead of a blank page;
  // starts on today's, steppable via the ◀/▶ buttons below
  const [featuredIdx, setFeaturedIdx] = useState(() => dayIndex(FEATURED.length))
  const featured = words.length === 0 ? FEATURED[featuredIdx] : null
  const chartWords = featured ? featured.words : words

  const wordsKey = chartWords.join(',')

  useEffect(() => {
    if (langs.length === 0) return
    getFilteredMovieIndex().then((idx) => setFilmCount(idx.length)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setTopMovies(null)
    setTopFilms(null)
    // featured trends chart reads its own pre-baked JSON (no tables); user words
    // read the per-word bake - chart + both tables in a few KB, no SQL engine
    // (a stale/missing bake degrades to the live engine inside loadTrends)
    if (featured) {
      loadFeaturedSeries(chartWords, COLORS)
        .then((ws) => {
          if (cancelled) return
          setWordSeries(ws)
          setSeries(ws.series)
          setPlottedYears(ws.plottedYears)
          setTrimmedYears(ws.trimmedYears)
          setMissing(ws.missing)
        })
        .catch((e) => !cancelled && setError(String(e)))
        .finally(() => !cancelled && setLoading(false))
    } else {
      loadTrends(chartWords, COLORS)
        .then(({ wordSeries, topMovies, topFilms }) => {
          if (cancelled) return
          setWordSeries(wordSeries)
          setSeries(wordSeries.series)
          setPlottedYears(wordSeries.plottedYears)
          setTrimmedYears(wordSeries.trimmedYears)
          setMissing(wordSeries.missing)
          setTopMovies(topMovies)
          setTopFilms(topFilms)
        })
        .catch((e) => !cancelled && setError(String(e)))
        .finally(() => !cancelled && setLoading(false))
    }
    return () => {
      cancelled = true
    }
  }, [wordsKey])

  // per-film mode re-divides the same counts by films per year (no refetch)
  const shownSeries = useMemo(() => {
    if (!series) return series
    return perFilm && wordSeries && films ? perFilmSeries({ ...wordSeries, series }, films) : series
  }, [series, wordSeries, films, perFilm])

  // graft top-movie notes onto the chart series once (if) they arrive
  const notedSeries = useMemo(() => {
    if (!shownSeries || !topMovies) return shownSeries
    return shownSeries.map((s) => ({
      ...s,
      points: s.points.map((p) => {
        const top = topMovies.get(s.name)?.get(p.x)
        return top ? { ...p, note: top.title, noteHref: `#/movie/${top.imdb_id}` } : p
      }),
    }))
  }, [shownSeries, topMovies])

  const addWord = () => {
    const w = input.trim().toLowerCase()
    if (!w) return
    setInput('')
    navigate(trendsHref([...new Set([...words, w])].slice(0, MAX_WORDS), perFilm))
  }

  return (
    <div>
      <p className="mt-1 text-sm text-ink-2">{perFilm ? t('trends.introPerFilm') : t('trends.intro')}</p>
      {langs.length > 0 && filmCount !== null && (
        <p className="mt-1 text-sm text-ink-2">
          {t('trends.languageNote', { count: n(filmCount), langs: langLabel })} <ExplainerLink />
        </p>
      )}

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          addWord()
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={words.length ? t('trends.addAnotherWordPlaceholder') : t('trends.firstWordPlaceholder')}
          aria-label={t('trends.wordInputAriaLabel')}
          className="w-64 border-2 border-ink bg-card px-3 py-2 font-script placeholder:text-ink-3"
        />
        <button type="submit" className="border-2 border-ink px-4 font-script font-bold uppercase hover:bg-mark">
          {t('trends.chartItButton')}
        </button>
      </form>

      {words.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2" role="list" aria-label={t('trends.chartedWordsAriaLabel')}>
          {words.map((w, i) => (
            <button
              key={w}
              onClick={() => navigate(trendsHref(words.filter((x) => x !== w), perFilm))}
              className="flex items-center gap-1.5 border-2 border-ink bg-card px-2.5 py-1 font-script text-sm hover:bg-paper-2"
              title={t('trends.removeWordTitle', { word: w })}
            >
              <span className="inline-block size-2.5 rounded-full" style={{ background: COLORS[i] }} />
              {w} ✕
            </button>
          ))}
        </div>
      )}

      {missing.length > 0 && !featured && (
        <p className="mt-3 font-script text-sm text-s2">
          {t('trends.notEnoughData', { words: missing.join(', ') })}
        </p>
      )}
      {langs.length > 0 && !loading && !error && chartWords.length > 0 && series !== null && series.length === 0 && (
        <p className="mt-3 font-script text-sm text-ink-2">
          {t('trends.notEnoughFilms', { langs: langLabel })}
        </p>
      )}
      {error && <ErrorBox message={error} />}
      {perFilm && filmsError && <ErrorBox message={filmsError} />}
      {loading && <Spinner label={t('trends.queryingCorpus')} />}
      {notedSeries && notedSeries.length > 0 && !loading && (!perFilm || films) && (
        <div className="mt-6 border-2 border-ink bg-card p-4">
          {featured && (
            <FeaturedNav
              className="mb-3 border-b-2 border-ink pb-2"
              title={t('trends.featuredPrefix', { title: featured.title })}
              idx={featuredIdx}
              len={FEATURED.length}
              noun={t('trends.navNoun')}
              suffix={t('trends.navSuffix')}
              onStep={(dir) => setFeaturedIdx((i) => stepFeatured(i, dir, FEATURED.length))}
            />
          )}
          <div className="mb-3 flex gap-1" role="group" aria-label={t('trends.measureAriaLabel')}>
            {([false, true] as const).map((on) => (
              <button
                key={String(on)}
                type="button"
                aria-pressed={perFilm === on}
                onClick={() => navigate(trendsHref(words, on))}
                className={`border-2 border-ink px-2.5 py-1 font-script text-xs ${perFilm === on ? 'bg-ink text-paper' : 'bg-card hover:bg-paper-2'}`}
              >
                {on ? t('trends.perFilmToggle') : t('trends.perMillionToggle')}
              </button>
            ))}
          </div>
          {/* legend built from the drawn series so colors always match,
              even if a featured word is missing from the dataset */}
          {featured && <SeriesLegend series={notedSeries} />}
          <LineChart series={notedSeries} yLabel={perFilm ? t('trends.yAxisLabelPerFilm') : t('trends.yAxisLabel')} />
          <p className="mt-2 text-end text-xs text-ink-2">
            {perFilm ? t('trends.usesPerFilmCaption') : t('trends.usesPerMillionWords')}
          </p>
          {trimmedYears !== null && (
            <p className="mt-1 text-end font-script text-xs text-ink-3">
              {t('trends.trimmedYearsNote', { years: trimmedYears })}
            </p>
          )}
          {!featured && wordSeries && films && (
            <div className="mt-3 space-y-0.5 border-t-2 border-ink pt-2 font-script text-sm">
              {words.map((w) => {
                const s = perFilmSummary(wordSeries, films, w)
                return s ? (
                  <p key={w}>
                    {t('trends.perFilmSummary', {
                      word: w,
                      latest: formatPerFilm(s.latest, n),
                      decade: s.decade,
                      overall: formatPerFilm(s.overall, n),
                    })}
                  </p>
                ) : null
              })}
            </div>
          )}
        </div>
      )}
      {words.length > 0 && !loading && !error && (
        // key resets the active tab whenever the word list changes
        <WordDetails
          key={words.join(',')}
          words={words}
          years={plottedYears}
          topMovies={topMovies}
          topFilms={topFilms}
        />
      )}
      {featured && !loading && <ShiftStrip />}
      {!words.length && (
        <div className="mt-8 font-script text-sm text-ink-2">
          <p>{t('trends.tryClassic')}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {['love', 'war', 'money', 'god', 'phone'].map((w) => (
              <button
                key={w}
                onClick={() => navigate(trendsHref([w], perFilm))}
                className="border-2 border-ink bg-card px-3 py-1 hover:bg-mark"
              >
                {w}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
