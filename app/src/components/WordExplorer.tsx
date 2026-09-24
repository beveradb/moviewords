import { useEffect, useMemo, useRef, useState } from 'react'
import { getMovieWords, type MovieWords } from '../lib/data'
import { navigate } from '../lib/route'
import {
  findWord, formatPer1k, listFor, movieWordsHash, onlyInFilm, pageOf, sortRows, stretchedVariants, type SortKey,
} from '../lib/wordExplorer'
import { Spinner } from './ui'
import { useI18n } from '../i18n'

/** "Every word in this film": linkable word search (?q=) with stretched
 * spellings, a sortable/paginated full list, and only-in-this-film words.
 * Loads json/words/<id>.json lazily - when scrolled into view, or at once if
 * the page was opened with ?q=. */
export function WordExplorer({ id, totalWords, initialQuery }: { id: string; totalWords: number; initialQuery: string }) {
  const { t, n } = useI18n()
  const ref = useRef<HTMLElement>(null)
  const [wanted, setWanted] = useState(Boolean(initialQuery))
  const [data, setData] = useState<MovieWords | null | undefined>(undefined) // undefined = not loaded yet
  const [q, setQ] = useState(initialQuery)
  const [sort, setSort] = useState<SortKey>('count')
  const [page, setPage] = useState(1)

  // a linked ?q= jumps straight to the section; otherwise load on first sight
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (initialQuery) {
      el.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      return
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setWanted(true)
        io.disconnect()
      }
    })
    io.observe(el)
    return () => io.disconnect()
  }, [initialQuery])

  useEffect(() => {
    if (!wanted) return
    let cancelled = false
    getMovieWords(id).then((d) => !cancelled && setData(d))
    return () => {
      cancelled = true
    }
  }, [id, wanted])

  const rows = useMemo(() => data?.w ?? [], [data])
  const exact = useMemo(() => findWord(rows, q), [rows, q])
  const variants = useMemo(() => stretchedVariants(rows, q), [rows, q])
  const listed = useMemo(() => sortRows(listFor(rows, q), sort), [rows, q, sort])
  const paged = pageOf(listed, page)
  const unique = useMemo(() => onlyInFilm(rows), [rows])
  const per1k = (c: number) => formatPer1k(c, totalWords, n)
  const query = q.trim().toLowerCase()

  const onQuery = (value: string) => {
    setQ(value)
    setPage(1)
    window.history.replaceState(null, '', movieWordsHash(id, value))
  }

  return (
    <section ref={ref} className="mt-10 scroll-mt-4">
      <h2 className="slug text-sm">{t('movie.everyWordHeading')}</h2>
      {data === undefined && wanted && <Spinner label={t('movie.loadingWords')} />}
      {data === null && <p className="mt-2 font-script text-sm text-ink-2">{t('movie.wordsUnavailable')}</p>}
      {data && (
        <>
          <p className="mt-1 text-xs text-ink-2">{t('movie.everyWordBody', { count: n(rows.length) })}</p>
          <input
            value={q}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={t('movie.findWordPlaceholder')}
            aria-label={t('movie.findWordAriaLabel')}
            className="mt-3 w-72 max-w-full border-2 border-ink bg-card px-3 py-2 font-script placeholder:text-ink-3"
          />

          {query && (
            <div className="mt-3 border-l-2 border-ink-3 pl-4 font-script text-sm">
              {exact ? (
                <p>
                  {t('movie.wordResult', { word: exact[0], count: n(exact[1]), rate: per1k(exact[1]), films: n(exact[2]) })}
                </p>
              ) : (
                <p>{t('movie.wordNotSaid', { word: query })}</p>
              )}
              {variants.length > 0 && (
                <p className="mt-1">
                  {t('movie.alsoWrittenAs')}{' '}
                  {variants.map(([w, c]) => (
                    <span key={w} className="me-3 whitespace-nowrap">
                      <b>{w}</b> ×{n(c)}
                    </span>
                  ))}
                </p>
              )}
              <button className="mt-1 text-xs underline hover:bg-mark" onClick={() => navigate(`/trends?w=${encodeURIComponent(query)}`)}>
                {t('movie.wordTrendLink', { word: query })}
              </button>
            </div>
          )}

          {unique.length > 0 && !query && (
            <div className="mt-5">
              <h3 className="slug text-xs">{t('movie.onlyInFilmHeading')}</h3>
              <p className="mt-1 text-xs text-ink-2">{t('movie.onlyInFilmBody')}</p>
              <p className="mt-2 font-script text-sm">
                {unique.map(([w, c]) => (
                  <span key={w} className="me-3 whitespace-nowrap">{w} <span className="text-ink-2">×{n(c)}</span></span>
                ))}
              </p>
            </div>
          )}

          <div className="mt-5 flex items-center gap-2 font-script text-xs">
            <label className="flex items-center gap-1.5">
              {t('movie.sortLabel')}
              <select
                value={sort}
                onChange={(e) => { setSort(e.target.value as SortKey); setPage(1) }}
                className="border-2 border-ink bg-card px-1.5 py-1 font-script text-xs"
              >
                <option value="count">{t('movie.sortCount')}</option>
                <option value="az">{t('movie.sortAz')}</option>
                <option value="rare">{t('movie.sortRare')}</option>
              </select>
            </label>
          </div>

          {listed.length === 0 ? (
            <p className="mt-3 font-script text-sm text-ink-2">{t('movie.noWordMatches', { q: query })}</p>
          ) : (
            <table className="mt-3 w-full font-script text-sm">
              <thead>
                <tr className="border-b-2 border-ink text-start text-xs uppercase tracking-wide text-ink-2">
                  <th scope="col" className="py-1 text-start">{t('movie.colWord')}</th>
                  <th scope="col" className="py-1 text-end">{t('movie.colCount')}</th>
                  <th scope="col" className="py-1 text-end">{t('movie.colPer1k')}</th>
                  <th scope="col" className="py-1 text-end">{t('movie.colFilms')}</th>
                </tr>
              </thead>
              <tbody>
                {paged.rows.map(([w, c, f]) => (
                  <tr key={w} className="border-b border-paper-2">
                    <td className="py-1">
                      <button className="hover:bg-mark" onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}>{w}</button>
                    </td>
                    <td className="py-1 text-end tabular-nums">{n(c)}</td>
                    <td className="py-1 text-end tabular-nums text-ink-2">{per1k(c)}</td>
                    <td className="py-1 text-end tabular-nums text-ink-2">{n(f)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {paged.pages > 1 && (
            <div className="mt-3 flex items-center gap-3 font-script text-xs">
              <button disabled={paged.page <= 1} onClick={() => setPage(paged.page - 1)} className="border-2 border-ink px-2 py-1 disabled:opacity-40">
                {t('movie.prevPage')}
              </button>
              <span>{t('movie.pageOf', { page: n(paged.page), pages: n(paged.pages) })}</span>
              <button disabled={paged.page >= paged.pages} onClick={() => setPage(paged.page + 1)} className="border-2 border-ink px-2 py-1 disabled:opacity-40">
                {t('movie.nextPage')}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
