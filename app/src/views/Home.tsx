import { useEffect, useState } from 'react'
import type { MovieIndexEntry } from '../lib/data'
import { getFilteredMovieIndex } from '../lib/data'
import { navigate } from '../lib/route'
import { MovieSearch, Poster } from '../components/ui'
import { FeaturedChart } from '../components/FeaturedChart'
import { ExplainerLink } from '../components/FilterExplainer'
import { EraMotif } from '../components/motifs'
import { activeLanguages, languageName } from '../lib/languages'
import { useI18n } from '../i18n'

const HOME_DECADES = ['1930', '1950', '1970', '1990', '2010']

const heroLink = (href: string, label: string) => (
  <a href={href} className="underline decoration-2 underline-offset-2 hover:bg-mark hover:text-ink">
    {label}
  </a>
)

/** Hero: the pitch on the left, the product on the right - a live featured
 * trend chart doing the explaining for anyone who won't read or scroll. */
function Hero({ count, words }: { count: number; words: number }) {
  const { t, tn, n } = useI18n()
  return (
    <div className="mt-8 grid items-start gap-8 sm:mt-12 lg:grid-cols-2">
      <div>
        <p className="font-script text-sm uppercase tracking-widest text-ink-2">{t('home.fadeIn')}</p>
        <h1 className="mt-3 max-w-2xl font-script text-4xl font-bold leading-tight sm:text-5xl">
          {tn('home.heroTitle', {
            vocabulary: (
              <span className="hl">
                <span className="hl-mark" style={{ width: 'calc(100% + 0.3em)' }} />
                <span className="hl-word">{t('home.heroVocabulary')}</span>
              </span>
            ),
          })}
        </h1>
        <p className="mt-4 max-w-xl text-ink-2">
          {tn('home.heroBody', {
            // Fallbacks match the all-films default corpus (shown until the movie index loads).
            count: n(count || 64579),
            millions: n(words ? Math.round(words / 1e6) : 469),
            trends: heroLink('#/trends?w=awesome,swell', t('home.heroTrends')),
            sweariest: heroLink('#/leaderboard?b=films', t('home.heroSweariest')),
            versus: heroLink('#/compare?e=tt0078748,tt0090605', t('home.heroVersus')),
          })}
        </p>
        <div className="mt-6 max-w-md">
          <MovieSearch onPick={(m) => navigate(`/movie/${m.id}`)} />
        </div>
      </div>
      <FeaturedChart />
    </div>
  )
}

export function HomeView() {
  const { t, tn, n, locale } = useI18n()
  const [featured, setFeatured] = useState<MovieIndexEntry[]>([])
  const [count, setCount] = useState(0)
  const [words, setWords] = useState(0)

  useEffect(() => {
    getFilteredMovieIndex()
      .then((idx) => {
        setCount(idx.length)
        setWords(idx.reduce((sum, m) => sum + m.total_words, 0))
        setFeatured(
          [...idx]
            .sort((a, b) => b.votes - a.votes)
            .slice(0, 60)
            .sort(() => 0.5 - Math.random())
            .slice(0, 8),
        )
      })
      .catch(() => {})
  }, [])

  return (
    <div>
      <Hero count={count} words={words} />

      {/* Shelf is always rendered (skeletons until data loads) so it reserves
          its height from first paint and never shifts the sections below it. */}
      <section className="mt-10">
        <h2 className="slug border-b-2 border-ink pb-1 text-sm">{t('home.shelfHeading')}</h2>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {((featured.length ? featured : Array.from({ length: 8 }, () => null)) as (MovieIndexEntry | null)[]).map(
            (m, i) =>
              m ? (
                <button
                  key={m.id}
                  onClick={() => navigate(`/movie/${m.id}`)}
                  className="border-2 border-ink bg-card text-start transition-transform hover:-translate-y-0.5 hover:shadow-[4px_4px_0_0_var(--color-ink)]"
                >
                  <Poster id={m.id} title={m.title} className="w-full border-b-2 border-ink" />
                  <div className="p-2.5">
                    <div className="line-clamp-2 font-script text-sm font-bold leading-snug">{m.title}</div>
                    <div className="mt-1 text-xs text-ink-2">
                      {t('home.movieMeta', { year: m.year, words: n(m.total_words) })}
                    </div>
                  </div>
                </button>
              ) : (
                <div key={`shelf-skeleton-${i}`} aria-hidden className="border-2 border-ink bg-card">
                  <div className="aspect-[2/3] w-full border-b-2 border-ink bg-paper-2" />
                  <div className="p-2.5">
                    <div className="h-4 w-4/5 rounded-sm bg-paper-2" />
                    <div className="mt-1.5 h-3 w-2/5 rounded-sm bg-paper-2" />
                  </div>
                </div>
              ),
          )}
        </div>
      </section>

      <section className="mt-10">
        <a
          href="#/decades"
          className="flex flex-wrap items-center justify-between gap-4 border-2 border-ink bg-card p-4 transition-transform hover:-translate-y-0.5 hover:shadow-[4px_4px_0_0_var(--color-ink)]"
        >
          <div>
            <h2 className="slug text-sm">{t('home.decadesHeading')}</h2>
            <p className="mt-1 text-sm text-ink-2">{t('home.decadesBody')}</p>
          </div>
          <div className="flex items-center gap-3 text-ink-3">
            {HOME_DECADES.map((d, i) => (
              <EraMotif key={d} decade={d} className={`h-11 w-11 ${i > 2 ? 'hidden sm:block' : ''}`} />
            ))}
            <span className="font-script text-sm font-bold text-ink">→</span>
          </div>
        </a>
      </section>

      <section className="mt-10 border-2 border-ink bg-paper-2 p-4 text-sm text-ink-2">
        <p className="font-script font-bold uppercase text-ink">{t('home.aboutHeading')}</p>
        <p className="mt-1">
          {tn('home.aboutBody', {
            count: (
              <strong>
                {t('home.aboutCountTemplate', {
                  count: count ? n(count) : t('home.aboutCountUnknown'),
                  kind:
                    activeLanguages().length === 0
                      ? t('home.aboutCountAllFilms')
                      : t('home.aboutCountLangFilms', {
                          langs: activeLanguages().map((c) => languageName(c, locale)).join(', '),
                        }),
                })}
              </strong>
            ),
            opus: (
              <a className="underline" href="https://opus.nlpl.eu/datasets/OpenSubtitles">
                {t('home.opusLink')}
              </a>
            ),
            faq: (
              <a className="underline" href="https://github.com/beveradb/moviewords/blob/main/docs/FAQ.md">
                {t('home.faqLink')}
              </a>
            ),
          })}
        </p>
        {activeLanguages().length > 0 && (
          <p className="mt-2">
            {t('home.aboutSubtitleHint')} <ExplainerLink />
          </p>
        )}
      </section>
    </div>
  )
}
