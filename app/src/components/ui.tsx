import { useEffect, useMemo, useRef, useState } from 'react'
import type { MovieIndexEntry } from '../lib/data'
import { getMovieIndex } from '../lib/data'
import { navigate } from '../lib/route'
import { ExplainerLink } from './FilterExplainer'
import { languageName } from '../lib/languages'
import type { Series } from './LineChart'
import { useI18n } from '../i18n'

/** ◀/▶ header row for a day-rotated featured pool (trends, matchups). */
export function FeaturedNav({
  title,
  idx,
  len,
  onStep,
  noun,
  suffix,
  className = '',
}: {
  title: string
  idx: number
  len: number
  onStep: (dir: 1 | -1) => void
  /** What one item is called in the aria labels, e.g. "trend" or "matchup". */
  noun: string
  suffix?: string
  className?: string
}) {
  const { t, n } = useI18n()
  const btn = (dir: 1 | -1, glyph: string) => (
    <button
      onClick={() => onStep(dir)}
      aria-label={t(dir === 1 ? 'ui.featuredNav.nextAriaLabel' : 'ui.featuredNav.prevAriaLabel', { noun })}
      className="border-2 border-ink px-2 font-script font-bold hover:bg-mark"
    >
      {glyph}
    </button>
  )
  return (
    <div className={`flex flex-wrap items-center justify-between gap-2 ${className}`}>
      <div className="flex items-center gap-2">
        {btn(-1, '◀')}
        {btn(1, '▶')}
        <h2 className="slug text-sm">{title}</h2>
      </div>
      <span className="font-script text-xs text-ink-2">
        {t('ui.featuredNav.position', { idx: n(idx + 1), len: n(len) })}
        {suffix ? ` - ${suffix}` : ''}
      </span>
    </div>
  )
}

/** Clickable chart legend - one chip per drawn series, linking into Trends. */
export function SeriesLegend({ series }: { series: Series[] }) {
  const { t } = useI18n()
  return (
    <div className="mb-3 flex flex-wrap gap-2 font-script text-sm">
      {series.map((s) => (
        <button
          key={s.name}
          onClick={() => navigate(`/trends?w=${encodeURIComponent(s.name)}`)}
          className="flex items-center gap-1.5 border-2 border-ink bg-paper px-2.5 py-0.5 hover:bg-mark"
          title={t('ui.seriesLegend.exploreTitle', { word: s.name })}
        >
          <span className="inline-block size-2.5 rounded-full" style={{ background: s.color }} />
          {s.name}
        </button>
      ))}
    </div>
  )
}

/** Screenplay slug-line header: INT. PULP FICTION - 1994 */
export function Slug({ prefix, text, right }: { prefix?: string; text: React.ReactNode; right?: React.ReactNode }) {
  const { t } = useI18n()
  return (
    <div className="slug flex items-baseline justify-between border-b-2 border-ink pb-1 text-sm sm:text-base">
      <span>
        {prefix ?? t('ui.slug.defaultPrefix')} {text}
      </span>
      {right && <span className="text-ink-2">{right}</span>}
    </div>
  )
}

/** The signature element: a word with a highlighter mark scaled to its count. */
export function HighlightWord({
  word,
  count,
  max,
  display,
  onClick,
}: {
  word: string
  count: number
  max: number
  /** Override for the right-hand figure (defaults to the count). */
  display?: string
  onClick?: () => void
}) {
  const { t, n } = useI18n()
  const frac = Math.max(count / max, 0.04)
  const displayText = display ?? n(count)
  return (
    <button
      onClick={onClick}
      className="group flex w-full items-baseline gap-3 rounded px-1 py-0.5 text-start hover:bg-paper-2"
      title={t('ui.highlightWord.title', { word, display: display ?? t('ui.highlightWord.spokenTimes', { count: n(count) }) })}
    >
      <span className="hl min-w-0 flex-1 font-script text-lg leading-6">
        <span className="hl-mark" style={{ width: `calc(${(frac * 100).toFixed(1)}% + 0.3em)` }} />
        <span className="hl-word">{word}</span>
      </span>
      <span className="ms-auto shrink-0 font-script text-sm text-ink-2 tabular-nums group-hover:text-ink">
        {displayText}
      </span>
    </button>
  )
}

/** "translated" marker for non-English originals - shown for any film whose
 * original language isn't English, regardless of the active language filter.
 * Clickable: opens the explainer (counts come from the English subtitles). */
export function LangBadge({ lang, className = '' }: { lang?: string; className?: string }) {
  const { locale } = useI18n()
  if (!lang || lang === 'en') return null
  const name = languageName(lang, locale)
  return <ExplainerLink variant="badge" badgeLang={name} className={className} />
}

const POSTER_BASE = 'https://data.moviewords.org/posters'

/** Movie poster from our R2 bucket, falling back to a script-cover placeholder. */
export function Poster({ id, title, className }: { id: string; title: string; className?: string }) {
  const { t } = useI18n()
  const [failed, setFailed] = useState(false)
  if (failed)
    return (
      <div
        className={`flex aspect-[2/3] items-center justify-center bg-paper-2 p-2 text-center font-script text-xs font-bold uppercase leading-tight text-ink-2 ${className ?? ''}`}
      >
        {title}
      </div>
    )
  // AVIF where supported, JPEG otherwise; `contents` keeps the <img> as the
  // layout box so callers' sizing classes and the reserved aspect ratio hold.
  return (
    <picture className="contents">
      <source srcSet={`${POSTER_BASE}/${id}.avif`} type="image/avif" />
      <img
        src={`${POSTER_BASE}/${id}.jpg`}
        alt={t('ui.poster.alt', { title })}
        loading="lazy"
        onError={() => setFailed(true)}
        className={`aspect-[2/3] object-cover ${className ?? ''}`}
      />
    </picture>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-ink-2">
      <span className="inline-block size-4 animate-spin rounded-full border-2 border-ink-3 border-t-ink" />
      <span className="font-script text-sm uppercase tracking-wide">{label}</span>
    </div>
  )
}

export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  const { t } = useI18n()
  return (
    <div className="my-6 border-2 border-s2 bg-paper-2 p-4 font-script text-sm">
      <p className="font-bold uppercase">{t('ui.errorBox.heading')}</p>
      <p className="mt-1 text-ink-2">{message}</p>
      {retry && (
        <button onClick={retry} className="mt-3 border-2 border-ink px-3 py-1 font-bold uppercase hover:bg-mark">
          {t('ui.errorBox.retryButton')}
        </button>
      )}
    </div>
  )
}

/** Debounced movie search over the small client-side index. */
export function MovieSearch({
  placeholder,
  onPick,
  autoFocus,
}: {
  placeholder?: string
  onPick: (m: MovieIndexEntry) => void
  autoFocus?: boolean
}) {
  const { t } = useI18n()
  const [index, setIndex] = useState<MovieIndexEntry[] | null>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getMovieIndex().then(setIndex).catch(() => setIndex([]))
  }, [])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const hits = useMemo(() => {
    if (!index || query.trim().length < 2) return []
    const needle = query.trim().toLowerCase()
    return index
      .filter((m) => m.title.toLowerCase().includes(needle))
      .sort((a, b) => b.votes - a.votes)
      .slice(0, 8)
  }, [index, query])

  return (
    <div ref={boxRef} className="relative">
      <input
        autoFocus={autoFocus}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder ?? t('ui.movieSearch.placeholder')}
        aria-label={t('ui.movieSearch.ariaLabel')}
        className="w-full border-2 border-ink bg-card px-3 py-2 font-script text-base placeholder:text-ink-3"
      />
      {open && hits.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full border-2 border-ink bg-card shadow-[4px_4px_0_0_var(--color-ink)]">
          {hits.map((m) => (
            <li key={m.id}>
              <button
                className="flex w-full items-baseline justify-between px-3 py-2 text-start font-script hover:bg-mark"
                onClick={() => {
                  onPick(m)
                  setQuery('')
                  setOpen(false)
                }}
              >
                <span className="truncate">{m.title}</span>
                <span className="ms-3 flex shrink-0 items-baseline gap-1.5">
                  <LangBadge lang={m.lang} />
                  <span className="text-sm text-ink-2">{m.year}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
