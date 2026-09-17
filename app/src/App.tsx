import { useEffect, useRef, useState } from 'react'
import { useRoute } from './lib/route'
import { trackPageview } from './lib/analytics'
import { activeLanguages, switchLanguages, getLanguages, languageName, type LanguageOption } from './lib/languages'
import { ExplainerLink } from './components/FilterExplainer'
import { LocaleFilterHint } from './components/LocaleFilterHint'
import { useI18n } from './i18n'
import { HomeView } from './views/Home'
import { GenresView } from './views/Genres'
import { DecadesView } from './views/Decades'
import { MovieView } from './views/Movie'
import { TrendsView } from './views/Trends'
import { LeaderboardView } from './views/Leaderboard'
import { CompareView } from './views/Compare'
import { EntityView } from './views/Entity'
import LanguageSelector from './components/LanguageSelector'

/** The site mark: a clapperboard whose slate reads as a highlighted line of
 * dialogue. Same geometry as public/favicon.svg, drawn with theme colors. */
function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <g transform="rotate(-4 32 32)">
        <path d="M6 10 L58 10 L58 24 L6 24 Z" fill="var(--color-ink)" />
        <g fill="var(--color-paper)">
          <path d="M12 10 L20 10 L14 24 L6 24 Z" />
          <path d="M28 10 L36 10 L30 24 L22 24 Z" />
          <path d="M44 10 L52 10 L46 24 L38 24 Z" />
        </g>
        <rect x="6" y="26" width="52" height="30" fill="var(--color-ink)" />
        <rect x="12" y="32" width="32" height="8" rx="3" fill="var(--color-mark)" transform="skewX(-4) translate(1 0)" />
        <rect x="12" y="45" width="22" height="4.5" rx="2.25" fill="var(--color-paper)" opacity="0.85" />
      </g>
    </svg>
  )
}

function ThemeToggle() {
  const { t } = useI18n()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const toggle = () => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }
  return (
    <button
      onClick={toggle}
      aria-label={dark ? t('themeToggle.switchToDay') : t('themeToggle.switchToNight')}
      title={dark ? t('themeToggle.dayShoot') : t('themeToggle.nightShoot')}
      className="flex h-8 items-center gap-1.5 border-2 border-ink px-2 font-script text-sm font-bold hover:bg-mark"
    >
      {dark ? (
        // sun
        <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" />
          <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1" />
        </svg>
      ) : (
        // moon
        <svg viewBox="0 0 24 24" className="size-3.5" fill="currentColor" aria-hidden="true">
          <path d="M20.6 14.6A9 9 0 1 1 9.4 3.4a7.2 7.2 0 1 0 11.2 11.2Z" />
        </svg>
      )}
      <span className="hidden sm:inline">{dark ? t('themeToggle.day') : t('themeToggle.night')}</span>
    </button>
  )
}

/** Original-language filter: a multiselect dropdown with a search box and a
 * film count per language. Selection is batched behind an Apply button that
 * persists + reloads - see lib/languages.ts. The globe hints that this is
 * where you narrow the corpus by language. */
function LanguageFilter() {
  const { t, n, locale } = useI18n()
  const [open, setOpen] = useState(false)
  const [opts, setOpts] = useState<LanguageOption[]>([])
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState<string[]>(() => activeLanguages())
  const ref = useRef<HTMLDivElement>(null)
  const active = activeLanguages()

  useEffect(() => { getLanguages().then(setOpts).catch(() => setOpts([])) }, [])
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const label = active.length === 0 ? t('languageFilter.allFilms')
    : active.length === 1 ? languageName(active[0], locale) : t('languageFilter.countLabel', { count: n(active.length) })
  const filtered = opts.filter((o) =>
    !query || languageName(o.code, locale).toLowerCase().includes(query.toLowerCase()) || o.code.includes(query.toLowerCase()))
  const toggle = (code: string) => setSel((s) => s.includes(code) ? s.filter((c) => c !== code) : [...s, code])
  const apply = () => switchLanguages(sel)
  // compare as sets, not order-sensitive lists - unchecking then rechecking a
  // language (or any other reordering) shouldn't read as a change and shuffle
  // ?langs= on Apply when membership is actually unchanged
  const dirty = [...sel].sort().join(',') !== [...active].sort().join(',')

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
        aria-label={t('languageFilter.ariaLabel')}
        className="flex h-8 items-center gap-1.5 border-2 border-ink px-2 font-script text-sm font-bold uppercase hover:bg-mark">
        <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" /><path d="M3 12h18" />
          <path d="M12 3c2.6 2.7 3.9 5.9 3.9 9s-1.3 6.3-3.9 9c-2.6-2.7-3.9-5.9-3.9-9S9.4 5.7 12 3Z" />
        </svg>
        {/* Hide the label on mobile only in the default state; when a filter is
            active, keep it visible so the narrowed corpus stays obvious. */}
        <span className={active.length === 0 ? 'hidden sm:inline' : ''}>{label}</span>
        <svg viewBox="0 0 24 24" className={`size-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div role="menu" aria-label={t('languageFilter.menuAriaLabel')} className="absolute right-0 z-20 mt-1 w-64 border-2 border-ink bg-paper font-script text-sm">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('languageFilter.searchPlaceholder')}
            className="w-full border-b-2 border-ink bg-transparent px-2.5 py-1.5 outline-none" aria-label={t('languageFilter.searchAriaLabel')} />
          <button onClick={() => setSel([])} aria-pressed={sel.length === 0}
            className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-bold uppercase ${sel.length === 0 ? 'bg-ink text-paper' : 'hover:bg-mark'}`}>
            <span aria-hidden="true" className="w-3">{sel.length === 0 ? '✓' : ''}</span> {t('languageFilter.allFilms')}
          </button>
          <div className="max-h-72 overflow-auto">
            {filtered.map((o) => (
              <button key={o.code} onClick={() => toggle(o.code)} role="menuitemcheckbox" aria-checked={sel.includes(o.code)}
                className={`flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left uppercase ${sel.includes(o.code) ? 'bg-mark' : 'hover:bg-mark'}`}>
                <span className="flex items-center gap-2"><span aria-hidden="true" className="w-3">{sel.includes(o.code) ? '✓' : ''}</span>{languageName(o.code, locale)}</span>
                <span className="text-ink-2">{n(o.films)}</span>
              </button>
            ))}
          </div>
          <button onClick={apply} disabled={!dirty}
            className="w-full border-t-2 border-ink px-2.5 py-1.5 font-bold uppercase disabled:opacity-40 hover:bg-mark">{t('languageFilter.apply')}</button>
          <p className="border-t-2 border-ink px-2.5 py-1.5 text-xs normal-case text-ink-2">
            {t('languageFilter.hint')}{' '}
            <ExplainerLink />
          </p>
        </div>
      )}
    </div>
  )
}

const TABS = [
  { hash: '#/', key: 'explore', match: '' },
  { hash: '#/genres', key: 'genres', match: 'genres' },
  { hash: '#/decades', key: 'decades', match: 'decades' },
  { hash: '#/trends', key: 'trends', match: 'trends' },
  { hash: '#/leaderboard', key: 'leaderboard', match: 'leaderboard' },
  { hash: '#/compare', key: 'compare', match: 'compare' },
]

export default function App() {
  const route = useRoute()
  const section = route.path[0] ?? ''
  const { t, tn } = useI18n()

  // Fire a GoatCounter pageview on first load and on every hash navigation.
  // Wrapped so the hashchange Event isn't passed as the retry counter.
  useEffect(() => {
    const track = () => trackPageview()
    track()
    window.addEventListener('hashchange', track)
    return () => window.removeEventListener('hashchange', track)
  }, [])

  // the Genres/Decades tabs stay lit on a specific study (#/genre/:id, #/decade/:id) too
  const isActive = (tab: (typeof TABS)[number]) =>
    section === tab.match ||
    (tab.match === 'genres' && section === 'genre') ||
    (tab.match === 'decades' && section === 'decade')

  return (
    <div className="mx-auto min-h-screen max-w-5xl px-4 pb-24 sm:px-6">
      <header className="flex flex-col gap-3 border-b-2 border-ink py-3">
        {/* Utility row: logo on the left, the three controls pushed right. On
            mobile the controls collapse to icons (see LanguageFilter/ThemeToggle)
            so they still fit beside the logo. */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <a href="#/" className="mr-auto flex items-center gap-2 font-script text-xl font-bold tracking-tight">
            <Logo className="size-7" />
            <span>
              MOVIE<span className="bg-mark px-0.5">WORDS</span>
            </span>
          </a>
          <div className="flex items-center gap-1.5">
            <LanguageFilter />
            <ThemeToggle />
            <LanguageSelector />
          </div>
        </div>
        <nav
          className="flex flex-wrap gap-0.5 font-script text-sm font-bold uppercase md:gap-1"
          aria-label={t('nav.sectionsLabel')}
        >
          {TABS.map((tab) => (
            <a
              key={tab.key}
              href={tab.hash}
              aria-current={isActive(tab) ? 'page' : undefined}
              className={`px-2.5 py-1.5 ${
                isActive(tab) ? 'bg-ink text-paper' : 'hover:bg-mark'
              }`}
            >
              {t('nav.' + tab.key)}
            </a>
          ))}
        </nav>
      </header>

      <main className="pt-4">
        <LocaleFilterHint />
        {section === '' && <HomeView />}
        {section === 'movie' && route.path[1] && <MovieView id={route.path[1]} />}
        {section === 'trends' && <TrendsView />}
        {section === 'genres' && <GenresView />}
        {section === 'decades' && <DecadesView />}
        {section === 'leaderboard' && <LeaderboardView />}
        {section === 'compare' && <CompareView />}
        {section === 'decade' && route.path[1] && <EntityView kind="decade" id={route.path[1]} />}
        {section === 'genre' && route.path[1] && <EntityView kind="genre" id={decodeURIComponent(route.path[1])} />}
      </main>

      <footer className="mt-20 border-t-2 border-ink pt-4 text-xs leading-5 text-ink-2">
        <p className="font-script font-bold uppercase text-ink">{t('footer.ideaHeading')}</p>
        <p className="mt-2">
          {tn('footer.ideaBody', {
            email: (
              <a className="underline" href="mailto:andrew@beveridge.uk?subject=Movie%20Words%20idea">
                {t('footer.ideaEmailLink')}
              </a>
            ),
          })}
        </p>

        <p className="mt-4 font-script font-bold uppercase text-ink">{t('footer.dataHeading')}</p>
        <p className="mt-2">
          {tn('footer.dataBody', {
            dataGuide: (
              <a
                className="underline"
                href="https://github.com/beveradb/moviewords/blob/main/docs/DATA.md"
              >
                {t('footer.dataGuideLink')}
              </a>
            ),
            license: (
              <a className="underline" href="https://creativecommons.org/licenses/by-nc-sa/4.0/">
                {t('footer.licenseLink')}
              </a>
            ),
            faq: (
              <a
                className="underline"
                href="https://github.com/beveradb/moviewords/blob/main/docs/FAQ.md"
              >
                {t('footer.faqLink')}
              </a>
            ),
          })}
        </p>

        <p className="mt-4 font-script font-bold uppercase text-ink">{t('footer.creditsHeading')}</p>
        <p className="mt-2">
          {tn('footer.creditsBody', {
            github: (
              <a className="underline" href="https://github.com/beveradb/moviewords">
                {t('footer.githubLink')}
              </a>
            ),
          })}
        </p>
        <p className="mt-1">
          {tn('footer.dataSourcesBody', {
            opus: (
              <a className="underline" href="https://opus.nlpl.eu/datasets/OpenSubtitles">
                {t('footer.opusLink')}
              </a>
            ),
            openSubtitles: (
              <a className="underline" href="http://www.opensubtitles.org/">
                {t('footer.openSubtitlesLink')}
              </a>
            ),
            imdbData: (
              <a className="underline" href="https://developer.imdb.com/non-commercial-datasets/">
                {t('footer.imdbDataLink')}
              </a>
            ),
            tmdb: (
              <a className="underline" href="https://www.themoviedb.org">
                {t('footer.tmdbLink')}
              </a>
            ),
            imdbUrl: (
              <a className="underline" href="https://www.imdb.com">
                {t('footer.imdbUrlLink')}
              </a>
            ),
          })}
        </p>
        <p className="mt-1">
          {tn('footer.tmdbDisclaimerBody', {
            takedown: (
              <a className="underline" href="mailto:andrew@beveridge.uk?subject=Movie%20Words%20takedown">
                {t('footer.takedownEmailLink')}
              </a>
            ),
          })}
        </p>
        <p className="mt-1">
          {tn('footer.madeByBody', {
            github: (
              <a className="underline" href="https://github.com/beveradb/">
                {t('footer.githubProfileLink')}
              </a>
            ),
            linkedin: (
              <a className="underline" href="https://www.linkedin.com/in/andrewbeveridge/">
                {t('footer.linkedinLink')}
              </a>
            ),
            instagram: (
              <a className="underline" href="https://www.instagram.com/beveradb/">
                {t('footer.instagramLink')}
              </a>
            ),
            lindsay: (
              <a className="underline" href="https://lindsaywright.design/">
                {t('footer.lindsayLink')}
              </a>
            ),
          })}
        </p>
      </footer>
    </div>
  )
}
