import { useEffect, useState } from 'react'
import type { MovieBlurb, MovieDetail, MovieIndexEntry, QualityFlag } from '../lib/data'
import { getMovie, getMovieBlurb, getMovieIndex } from '../lib/data'
import { navigate, useRoute } from '../lib/route'
import { ErrorBox, HighlightWord, LangBadge, Poster, Slug, Spinner } from '../components/ui'
import { WordFilterBar, defaultFilter, passesFilter, type WordRow } from '../components/WordFilter'
import { WordExplorer } from '../components/WordExplorer'
import { useI18n } from '../i18n'

function Stat({ label, value, href }: { label: string; value: string; href?: string }) {
  const inner = (
    <>
      <div className="font-script text-2xl font-bold tabular-nums">{value}</div>
      <div className="mt-0.5 text-xs uppercase tracking-wide text-ink-2">{label}</div>
    </>
  )
  const cls = 'block border-2 border-ink bg-card px-4 py-3'
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`${cls} hover:bg-mark`}>
      {inner}
    </a>
  ) : (
    <div className={cls}>{inner}</div>
  )
}

const QUALITY_KEYS: Record<QualityFlag, string> = {
  asr: 'movie.qualityAsr',
  'machine-translated': 'movie.qualityMachineTranslated',
  'wrong-cast': 'movie.qualityWrongCast',
  anachronism: 'movie.qualityAnachronism',
}

/** Why a film's numbers are left out of the site's aggregates. */
function QualityNote({ flags }: { flags: QualityFlag[] }) {
  const { t } = useI18n()
  return (
    <div role="note" className="mt-5 border-2 border-s2 bg-paper-2 p-4 font-script text-sm">
      <p className="font-bold uppercase">{t('movie.qualityHeading')}</p>
      {flags.map((f) => (
        <p key={f} className="mt-1 text-ink-2">
          {t(QUALITY_KEYS[f])}
        </p>
      ))}
      <p className="mt-1 text-ink-2">{t('movie.qualityExcluded')}</p>
    </div>
  )
}

export function MovieView({ id }: { id: string }) {
  const { t, n, tn } = useI18n()
  const { params } = useRoute()
  const [movie, setMovie] = useState<MovieDetail | null>(null)
  const [meta, setMeta] = useState<MovieIndexEntry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState(defaultFilter())
  const [blurb, setBlurb] = useState<MovieBlurb | null>(null)

  useEffect(() => {
    setMovie(null)
    setError(null)
    getMovie(id)
      .then(setMovie)
      .catch(() => setError(t('movie.notFound', { id })))
    getMovieIndex().then((idx) => setMeta(idx.find((m) => m.id === id) ?? null)).catch(() => {})
    setBlurb(null)
    getMovieBlurb(id).then(setBlurb).catch(() => {})
  }, [id, t])

  if (error) return <ErrorBox message={error} retry={() => navigate('/')} />
  if (!movie) return <Spinner label={t('movie.loadingScript')} />

  const imdbUrl = `https://www.imdb.com/title/${movie.imdb_id}/`
  const decade = Math.floor(movie.year / 10) * 10

  // 'all words' mode merges the raw head (stopwords included) with the wider
  // stopword-free top list, so mid-list common words stay reachable
  const allRows = filter.common === 'all'
    ? [...new Map([...movie.top, ...movie.top_all].map((r) => [r[0], r])).values()].sort((a, b) => b[1] - a[1])
    : movie.top
  const words = allRows.filter((r) => passesFilter(r as WordRow, filter)).slice(0, 25)
  // signature words are already statistically distinctive - only kind chips
  // apply, not the commonness toggle (log-odds may rightly pick zipf≥5 words)
  const distinctive = movie.distinctive
    .filter((r) => passesFilter(r as WordRow, { ...filter, common: 'all' }))
    .slice(0, 20)
  const sigMax = distinctive.length ? distinctive[0][1] : 1

  return (
    <div>
      <Slug
        text={tn('movie.slugTitle', {
          title: movie.title,
          year: (
            <a
              href={`#/decade/${decade}`}
              className="hover:bg-mark"
              title={t('movie.decadeLinkTitle', { decade })}
            >
              {movie.year}
            </a>
          ),
        })}
        right={
          <span className="inline-flex items-baseline gap-2">
            <LangBadge lang={meta?.lang ?? movie.original_language} />
            <span>
              {[...new Set(meta?.genres ?? [])].slice(0, 3).map((g, i) => (
                <span key={g}>
                  {i > 0 && t('movie.genreSeparator')}
                  <a href={`#/genre/${encodeURIComponent(g)}`} className="hover:bg-mark">
                    {t('genres.' + g)}
                  </a>
                </span>
              ))}
            </span>
          </span>
        }
      />

      {movie.quality && <QualityNote flags={movie.quality.flags.filter((f) => f in QUALITY_KEYS)} />}

      <div className="mt-5 flex gap-4">
        <a
          href={imdbUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="w-28 shrink-0 sm:w-36"
          title={t('movie.imdbPosterTitle', { title: movie.title })}
        >
          <Poster id={movie.imdb_id} title={movie.title} className="w-full border-2 border-ink" />
        </a>
        <div className="grid flex-1 grid-cols-2 content-start gap-3 sm:grid-cols-3">
          <Stat label={t('movie.wordsSpokenLabel')} value={n(movie.stats.total_words)} />
          <Stat label={t('movie.distinctWordsLabel')} value={n(movie.stats.unique_words)} />
          <Stat
            label={t('movie.vocabRichnessLabel')}
            value={n(movie.stats.unique_words / movie.stats.total_words, {
              style: 'percent',
              minimumFractionDigits: 1,
              maximumFractionDigits: 1,
            })}
          />
          <Stat
            label={t('movie.wordsPerMinuteLabel')}
            value={movie.stats.words_per_minute != null ? n(Math.round(movie.stats.words_per_minute)) : '—'}
          />
          <Stat
            label={t('movie.runtimeLabel')}
            value={blurb?.runtime ? t('movie.runtimeValue', { minutes: blurb.runtime }) : '—'}
          />
          <Stat
            label={t('movie.imdbRatingLabel')}
            value={meta ? n(meta.rating, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '—'}
            href={imdbUrl}
          />
        </div>
      </div>

      {(blurb?.tagline || blurb?.overview) && (
        <div className="mt-5 border-l-2 border-ink-3 pl-4">
          {blurb.tagline && <p className="font-script text-sm italic text-ink-2">“{blurb.tagline}”</p>}
          {blurb.overview && <p className="mt-1 max-w-prose text-sm text-ink">{blurb.overview}</p>}
        </div>
      )}

      <WordFilterBar filter={filter} onChange={setFilter} />

      <div className="mt-8 grid gap-10 md:grid-cols-2">
        {/* Signature words lead and get the highlighter - they're the story. */}
        <section>
          <h2 className="slug text-sm">{t('movie.signatureWordsHeading')}</h2>
          <p className="mt-1 text-xs text-ink-2">{t('movie.signatureWordsBody')}</p>
          <div className="mt-3">
            {distinctive.map(([w, z]) => (
              <HighlightWord
                key={w}
                word={w}
                count={z}
                max={sigMax}
                display={n(z, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}
              />
            ))}
          </div>
        </section>

        <section>
          <h2 className="slug text-sm">{t('movie.mostSpokenHeading')}</h2>
          <ol className="mt-3 grid grid-cols-2 gap-x-6">
            {words.map(([w, c], i) => (
              <li key={w} className="flex items-baseline gap-2 border-b border-paper-2 py-1.5 font-script">
                <span className="w-5 text-end text-xs text-ink-3">{i + 1}</span>
                <button className="hover:bg-mark" onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}>
                  {w}
                </button>
                <span className="ms-auto text-xs tabular-nums text-ink-2">{n(c)}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <WordExplorer key={id} id={id} totalWords={movie.stats.total_words} initialQuery={params.get('q') ?? ''} />

      <div className="mt-10 flex gap-3">
        <button
          onClick={() => navigate(`/compare?ids=${id}`)}
          className="border-2 border-ink px-4 py-2 font-script font-bold uppercase hover:bg-mark"
        >
          {t('movie.compareButton')}
        </button>
      </div>
    </div>
  )
}
