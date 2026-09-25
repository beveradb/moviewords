import { useEffect, useMemo, useState } from 'react'
import type { MovieIndexEntry, SignatureEntry } from '../lib/data'
import { getMovie, getMovieIndex, getSignatures, getWordlists, inCorpus } from '../lib/data'
import { headToHead } from '../lib/compare'
import { lit, pq, q } from '../lib/duck'
import { navigate, useRoute } from '../lib/route'
import { Sparkline } from '../components/LineChart'
import { ErrorBox, FeaturedNav, MovieSearch, Slug, Spinner } from '../components/ui'
import { MATCHUPS, dayIndex, stepFeatured } from '../lib/featured'
import { useI18n } from '../i18n'

const COLORS = ['var(--color-s1)', 'var(--color-s2)', 'var(--color-s3)']
const MAX = 3

/** URL entity encoding: movie ids verbatim, decades as d:1980, genres as g:Crime. */
interface EntityRef {
  kind: 'movie' | 'decade' | 'genre'
  id: string
}

interface EntityCard {
  ref: EntityRef
  /** Movie title/year - only set for kind: 'movie' cards; decade/genre cards
   * derive their label from ref.id at render time so it re-localizes without
   * a refetch. */
  title?: string
  year?: number
  films: number
  totalWords: number
  signature: [string, number][]
  /** [word, count] source for head-to-head rates. */
  words: [string, number][]
  uniqueWords?: number
  swearsPer1k?: number
}

const parseRef = (s: string): EntityRef =>
  s.startsWith('d:')
    ? { kind: 'decade', id: s.slice(2) }
    : s.startsWith('g:')
      ? { kind: 'genre', id: s.slice(2) }
      : { kind: 'movie', id: s }

const encodeRef = (r: EntityRef) =>
  r.kind === 'decade' ? `d:${r.id}` : r.kind === 'genre' ? `g:${r.id}` : r.id

async function loadCard(ref: EntityRef): Promise<EntityCard | null> {
  try {
    if (ref.kind === 'movie') {
      const m = await getMovie(ref.id)
      const words = new Map<string, number>()
      for (const [w, c] of [...m.top_all, ...m.top]) words.set(w as string, c as number)
      return {
        ref,
        title: m.title,
        year: m.year,
        films: 1,
        totalWords: m.stats.total_words,
        signature: m.distinctive,
        words: [...words.entries()],
        uniqueWords: m.stats.unique_words,
      }
    }
    const sig: SignatureEntry | undefined = (await getSignatures(
      ref.kind === 'decade' ? 'decades' : 'genres',
    ))[ref.id]
    if (!sig) return null
    return {
      ref,
      films: sig.movie_count,
      totalWords: sig.total_words,
      signature: sig.signature,
      words: sig.top_words ?? sig.top,
      uniqueWords: sig.unique_words,
      swearsPer1k: sig.swears_per_1k,
    }
  } catch {
    return null
  }
}

/** Swears/1k for movie entities via one DuckDB query (pre-baked for decades/genres). */
function useSwears(movieIds: string[]) {
  const [swears, setSwears] = useState<Map<string, number>>(new Map())
  useEffect(() => {
    if (movieIds.length === 0) return
    let cancelled = false
    getWordlists()
      .then((wl) =>
        q<{ imdb_id: string; swears: number }>(
          `SELECT imdb_id, SUM(count)::DOUBLE AS swears FROM ${pq('words_by_movie/data.parquet')}
           WHERE imdb_id IN (${movieIds.map(lit).join(',')})
             AND word IN (${wl.profanity.map(lit).join(',')})
           GROUP BY imdb_id`,
        ),
      )
      .then((rows) => {
        if (cancelled) return
        const m = new Map(movieIds.map((id) => [id, 0]))
        rows.forEach((r) => m.set(r.imdb_id, r.swears))
        setSwears(m)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [movieIds.join(',')])
  return swears
}

/** Films-per-year mini trend for decade/genre cards, from the client-side index. */
function FilmsPerYear({ entityRef, color }: { entityRef: EntityRef; color: string }) {
  const { t } = useI18n()
  const [index, setIndex] = useState<MovieIndexEntry[] | null>(null)
  useEffect(() => {
    getMovieIndex()
      .then((idx) => setIndex(idx.filter(inCorpus)))
      .catch(() => {})
  }, [])
  const points = useMemo(() => {
    if (!index) return []
    const per = new Map<number, number>()
    for (const m of index) {
      // genres can be null in the index for films TMDB knows no genres for
      if (entityRef.kind === 'genre' && !(m.genres ?? []).includes(entityRef.id)) continue
      if (entityRef.kind === 'decade' && Math.floor(m.year / 10) * 10 !== Number(entityRef.id)) continue
      per.set(m.year, (per.get(m.year) ?? 0) + 1)
    }
    return [...per.entries()].sort((a, b) => a[0] - b[0]) as [number, number][]
  }, [index, entityRef.kind, entityRef.id])
  if (points.length < 2) return null
  return (
    <div className="flex items-center gap-2" title={t('compare.filmsPerYearTitle')}>
      <Sparkline points={points} color={color} width={130} height={22} />
      <span className="text-[10px] uppercase text-ink-3">{t('compare.filmsPerYearLabel')}</span>
    </div>
  )
}

function EntityPicker({ refs }: { refs: EntityRef[] }) {
  const { t } = useI18n()
  const [decades, setDecades] = useState<string[]>([])
  const [genres, setGenres] = useState<string[]>([])
  useEffect(() => {
    getSignatures('decades').then((d) => setDecades(Object.keys(d).sort())).catch(() => {})
    getSignatures('genres').then((g) => setGenres(Object.keys(g).sort())).catch(() => {})
  }, [])
  const add = (ref: EntityRef) =>
    navigate(`/compare?e=${[...refs, ref].map(encodeRef).join(',')}`)
  const selectCls = 'border-2 border-ink bg-card px-2 py-2 font-script text-sm'
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <div className="w-64">
        <MovieSearch
          placeholder={refs.length ? t('compare.addFilmPlaceholder') : t('compare.pickFilmPlaceholder')}
          onPick={(m) => add({ kind: 'movie', id: m.id })}
        />
      </div>
      <span className="font-script text-xs uppercase text-ink-2">{t('compare.orLabel')}</span>
      <select
        className={selectCls}
        value=""
        aria-label={t('compare.addDecadeAriaLabel')}
        onChange={(e) => e.target.value && add({ kind: 'decade', id: e.target.value })}
      >
        <option value="">{t('compare.addDecadeOption')}</option>
        {decades.map((d) => (
          <option key={d} value={d}>
            {t('compare.decadeOptionLabel', { decade: d })}
          </option>
        ))}
      </select>
      <select
        className={selectCls}
        value=""
        aria-label={t('compare.addGenreAriaLabel')}
        onChange={(e) => e.target.value && add({ kind: 'genre', id: e.target.value })}
      >
        <option value="">{t('compare.addGenreOption')}</option>
        {genres.map((g) => (
          <option key={g} value={g}>
            {t('genres.' + g)}
          </option>
        ))}
      </select>
    </div>
  )
}

const wordChip = (w: string, extra = '') => (
  <button
    key={w}
    onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}
    className={`me-2 text-start font-script hover:bg-mark ${extra}`}
  >
    {w}
  </button>
)

export function CompareView() {
  const { t, tn, n } = useI18n()
  const { params } = useRoute()
  const refs = useMemo(
    () =>
      (params.get('e') ?? params.get('ids') ?? '')
        .split(',')
        .filter(Boolean)
        .map(parseRef)
        .slice(0, MAX),
    [params],
  )
  // empty URL → today's featured matchup, so the page always shows a comparison;
  // starts on today's, steppable via the ◀/▶ buttons below
  const [featuredIdx, setFeaturedIdx] = useState(() => dayIndex(MATCHUPS.length))
  const featured = refs.length === 0 ? MATCHUPS[featuredIdx] : null
  const activeRefs = useMemo(
    () => (featured ? featured.e.split(',').map(parseRef) : refs),
    [featured, refs],
  )
  const [cards, setCards] = useState<(EntityCard | null)[] | null>(null)
  const movieIds = useMemo(
    () => activeRefs.filter((r) => r.kind === 'movie').map((r) => r.id),
    [activeRefs],
  )
  const swears = useSwears(movieIds)

  useEffect(() => {
    let cancelled = false
    setCards(null)
    Promise.all(activeRefs.map(loadCard)).then((cs) => !cancelled && setCards(cs))
    return () => {
      cancelled = true
    }
  }, [activeRefs.map(encodeRef).join(',')])

  // memoized so the h2h/shared memos below actually cache between renders
  const loaded = useMemo(() => (cards ?? []).filter((c): c is EntityCard => c !== null), [cards])

  const h2h = useMemo(() => {
    if (loaded.length < 2) return null
    return headToHead(
      loaded.map((c) => ({ key: encodeRef(c.ref), totalWords: c.totalWords, words: c.words })),
    )
  }, [loaded])

  const shared = useMemo(() => {
    if (loaded.length < 2) return []
    const sets = loaded.map((c) => new Set(c.signature.map(([w]) => w)))
    return [...sets[0]].filter((w) => sets.every((s) => s.has(w))).slice(0, 15)
  }, [loaded])
  const sharedSet = useMemo(() => new Set(shared), [shared])

  // decade/genre cards derive their label from ref.id at render time (rather
  // than a value baked in by loadCard) so it re-localizes on locale switch
  // without a refetch.
  const cardLabel = (c: EntityCard) =>
    c.ref.kind === 'movie'
      ? t('compare.movieLabel', { title: c.title ?? '', year: c.year ?? '' })
      : c.ref.kind === 'decade'
        ? t('compare.decadeLabel', { decade: c.ref.id })
        : t('genres.' + c.ref.id)

  return (
    <div>
      <p className="mt-1 text-sm text-ink-2">{t('compare.introBody')}</p>
      {refs.length < MAX && <EntityPicker refs={refs} />}
      {featured && (
        <FeaturedNav
          className="mt-5"
          title={t('compare.featuredMatchupPrefix', { title: featured.title })}
          idx={featuredIdx}
          len={MATCHUPS.length}
          noun={t('compare.navNoun')}
          suffix={t('compare.navSuffix')}
          onStep={(dir) => setFeaturedIdx((i) => stepFeatured(i, dir, MATCHUPS.length))}
        />
      )}
      {cards === null && <Spinner label={t('compare.loadingLabel')} />}
      {cards !== null && loaded.length === 0 && (
        // reload rather than navigate: on the featured (empty-URL) state the
        // hash wouldn't change, so navigating re-fetches nothing
        <ErrorBox message={t('compare.nothingFoundMessage')} retry={() => window.location.reload()} />
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {loaded.map((c, i) => {
          const per1k =
            c.ref.kind === 'movie'
              ? swears.has(c.ref.id)
                ? (swears.get(c.ref.id)! / c.totalWords) * 1000
                : null
              : (c.swearsPer1k ?? null)
          return (
            <section key={encodeRef(c.ref)} className="border-2 border-ink bg-card">
              <div
                className="border-b-2 border-ink px-4 py-2"
                style={{ background: `color-mix(in srgb, ${COLORS[i]} 14%, transparent)` }}
              >
                <Slug prefix={`${i + 1}.`} text={cardLabel(c)} />
                <div className="mt-1 flex items-center justify-between gap-2">
                  {refs.length > 0 ? (
                    <button
                      onClick={() =>
                        navigate(
                          `/compare?e=${refs
                            .filter((r) => encodeRef(r) !== encodeRef(c.ref))
                            .map(encodeRef)
                            .join(',')}`,
                        )
                      }
                      className="text-xs text-ink-2 underline hover:text-ink"
                    >
                      {t('compare.removeButton')}
                    </button>
                  ) : (
                    <span />
                  )}
                  {c.ref.kind !== 'movie' && <FilmsPerYear entityRef={c.ref} color={COLORS[i]} />}
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3 font-script text-sm">
                <dt className="text-ink-2">{t('compare.filmsLabel')}</dt>
                <dd className="text-end tabular-nums">{n(c.films)}</dd>
                <dt className="text-ink-2">{t('compare.wordsSpokenLabel')}</dt>
                <dd className="text-end tabular-nums">{n(c.totalWords)}</dd>
                {c.ref.kind !== 'movie' && (
                  <>
                    <dt className="text-ink-2">{t('compare.wordsPerFilmLabel')}</dt>
                    <dd className="text-end tabular-nums">
                      {n(Math.round(c.totalWords / Math.max(c.films, 1)))}
                    </dd>
                  </>
                )}
                {c.uniqueWords !== undefined && (
                  <>
                    <dt className="text-ink-2">{t('compare.distinctWordsLabel')}</dt>
                    <dd className="text-end tabular-nums">{n(c.uniqueWords)}</dd>
                  </>
                )}
                {per1k !== null && (
                  <>
                    <dt className="text-ink-2">{t('compare.swearsPer1kLabel')}</dt>
                    <dd className="text-end tabular-nums">
                      {n(per1k, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                    </dd>
                  </>
                )}
              </dl>
              <div className="border-t-2 border-paper-2 px-4 py-3">
                <h3 className="text-xs uppercase tracking-wide text-ink-2">
                  {tn('compare.signatureWordsHeading', {
                    note: <span className="normal-case">{t('compare.signatureWordsHighlightedNote')}</span>,
                  })}
                </h3>
                <p className="mt-1.5 font-script text-sm leading-6">
                  {c.signature.slice(0, 16).map(([w]) => wordChip(w, sharedSet.has(w) ? 'bg-mark px-0.5' : ''))}
                </p>
              </div>
              {c.ref.kind === 'movie' && (
                <div className="px-4 pb-3">
                  <a href={`#/movie/${c.ref.id}`} className="font-script text-xs underline">
                    {t('compare.fullBreakdownLink')}
                  </a>
                </div>
              )}
            </section>
          )
        })}
      </div>

      {h2h && (
        <div className="mt-8 border-2 border-ink bg-card p-4">
          <h2 className="slug text-sm">{t('compare.headToHeadHeading')}</h2>
          <p className="mt-1 text-xs text-ink-2">
            {t(loaded.length > 2 ? 'compare.headToHeadIntroMany' : 'compare.headToHeadIntroPair')}
          </p>
          <div className="mt-3 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {loaded.map((c, i) => {
              const rows = h2h.get(encodeRef(c.ref)) ?? []
              return (
                <section key={encodeRef(c.ref)}>
                  <h3
                    className={`border-b border-paper-2 pb-1 font-script text-sm font-bold${
                      c.ref.kind === 'genre' ? ' uppercase' : ''
                    }`}
                    style={{ color: COLORS[i] }}
                  >
                    {cardLabel(c)}
                  </h3>
                  {rows.length === 0 && (
                    <p className="mt-2 font-script text-xs text-ink-3">{t('compare.noStandoutWords')}</p>
                  )}
                  <ol className="mt-2">
                    {rows.map((r) => (
                      <li key={r.word} className="flex items-baseline gap-2 py-0.5 font-script text-sm">
                        {wordChip(r.word, 'font-bold')}
                        <span className="ms-auto shrink-0 text-xs tabular-nums text-ink-2">
                          {t('compare.ratioMoreLabel', {
                            ratio: n(r.ratio >= 10 ? Math.round(r.ratio) : r.ratio, { maximumFractionDigits: 1 }),
                          })}
                        </span>
                      </li>
                    ))}
                  </ol>
                </section>
              )
            })}
          </div>
        </div>
      )}

      {shared.length > 0 && (
        <div className="mt-8 border-2 border-ink bg-card p-4">
          <h2 className="slug text-sm">{t('compare.sharedSignatureWordsHeading')}</h2>
          <p className="mt-2 font-script">{shared.map((w) => wordChip(w, 'me-3 bg-mark px-1'))}</p>
        </div>
      )}
    </div>
  )
}
