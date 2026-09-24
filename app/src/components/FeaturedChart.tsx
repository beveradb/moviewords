import { useEffect, useState } from 'react'
import type { Series } from './LineChart'
import { LineChart } from './LineChart'
import { loadFeaturedSeries } from '../lib/series'
import { FEATURED, dayIndex, stepFeatured } from '../lib/featured'
import { FeaturedNav, SeriesLegend, Spinner } from './ui'
import { useI18n } from '../i18n'

const COLORS = ['var(--color-s1)', 'var(--color-s2)', 'var(--color-s3)', 'var(--color-s4)']

/** Self-contained featured-trend chart for the homepage hero: starts on
 * today's featured shift, steppable with ◀/▶ like the Trends page. Charts
 * from the pre-baked featured-series JSON when the words are in the bake
 * (no SQL engine), falling back to a live word_year.parquet query. Data
 * loads in an effect so it never blocks first paint; if a query fails the
 * stepper stays so the visitor can move on to a trend that works. */
export function FeaturedChart() {
  const { t } = useI18n()
  const [idx, setIdx] = useState(() => dayIndex(FEATURED.length))
  const [series, setSeries] = useState<Series[] | null>(null)
  const [failed, setFailed] = useState(false)
  const featured = FEATURED[idx]

  useEffect(() => {
    let cancelled = false
    setSeries(null)
    setFailed(false)
    loadFeaturedSeries(featured.words, COLORS)
      .then(({ series }) => !cancelled && setSeries(series))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [featured.words.join(',')])

  return (
    <div className="border-2 border-ink bg-card p-4">
      <FeaturedNav
        className="mb-2 border-b-2 border-ink pb-2"
        title={featured.title}
        idx={idx}
        len={FEATURED.length}
        noun={t('chart.trendNoun')}
        onStep={(dir) => setIdx((i) => stepFeatured(i, dir, FEATURED.length))}
      />
      {/* Reserve the body height so the spinner -> chart swap doesn't shift the
          page (min-h fits the loaded legend+chart+caption at mobile widths). */}
      <div className="flex min-h-[210px] flex-col justify-center">
        {failed ? (
          <p className="py-8 text-center font-script text-sm text-ink-2">
            {t('chart.loadFailedMessage')}
          </p>
        ) : series === null ? (
          <Spinner label={t('chart.chartingSpinner')} />
        ) : (
          <>
            <SeriesLegend series={series} />
            <LineChart series={series} yLabel={t('chart.yAxisLabel')} />
            <p className="mt-1 flex items-baseline justify-between gap-2 text-xs text-ink-2">
              <a href="#/trends" className="font-script underline hover:bg-mark">
                {t('chart.moreTrendsLink')}
              </a>
              <span>{t('chart.usesPerMillionCaption')}</span>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
