import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { togglePin } from '../lib/trends'
import { useI18n } from '../i18n'
import { formatChartValue } from '../lib/chartFormat'

export interface Series {
  name: string
  color: string
  /** note: extra context rendered under the series row in the tooltip;
   * noteHref makes it a link */
  points: { x: number; y: number; note?: string; noteHref?: string }[]
}

const M = { top: 12, right: 16, bottom: 26, left: 46 }

/** Tiny inline trend line for list rows and compare cards. */
export function Sparkline({
  points,
  width = 110,
  height = 26,
  color = 'var(--color-s1)',
}: {
  points: [number, number][]
  width?: number
  height?: number
  color?: string
}) {
  if (points.length < 2) return null
  const xs = points.map((p) => p[0])
  const ys = points.map((p) => p[1])
  const xMin = Math.min(...xs)
  const xSpan = Math.max(...xs) - xMin || 1
  const yMax = Math.max(...ys) || 1
  const path = points
    .map(([x, y]) => `${(((x - xMin) / xSpan) * (width - 2) + 1).toFixed(1)},${(height - 2 - (y / yMax) * (height - 4)).toFixed(1)}`)
    .join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="shrink-0" aria-hidden>
      <polyline fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" points={path} />
    </svg>
  )
}

/** Multi-series line chart (SVG) with crosshair + tooltip per the dataviz spec. */
export function LineChart({
  series,
  width = 720,
  height = 300,
  yLabel,
}: {
  series: Series[]
  width?: number
  height?: number
  yLabel: string
}) {
  const { t } = useI18n()
  const svgRef = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [hoverX, setHoverX] = useState<number | null>(null)
  const [pinned, setPinned] = useState<number[]>([])

  const { xs, xMin, xMax, yMax } = useMemo(() => {
    const xs = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b)
    const ys = series.flatMap((s) => s.points.map((p) => p.y))
    return { xs, xMin: Math.min(...xs), xMax: Math.max(...xs), yMax: Math.max(...ys) > 0 ? Math.max(...ys) : 1 }
  }, [series])

  if (series.length === 0 || xs.length === 0) return null
  const iw = width - M.left - M.right
  const ih = height - M.top - M.bottom
  const sx = (x: number) => M.left + (xMax === xMin ? iw / 2 : ((x - xMin) / (xMax - xMin)) * iw)
  const sy = (y: number) => M.top + ih - (y / yMax) * ih

  const yTicks = useMemo(() => {
    const step = Math.pow(10, Math.floor(Math.log10(yMax)))
    const n = yMax / step
    const size = n >= 5 ? step : n >= 2 ? step / 2 : step / 5
    const ticks: number[] = []
    for (let v = 0; v <= yMax * 1.001; v += size) ticks.push(v)
    return ticks
  }, [yMax])

  const xTicks = useMemo(() => {
    const span = xMax - xMin
    const step = span > 60 ? 20 : span > 25 ? 10 : span > 12 ? 5 : 1
    const ticks: number[] = []
    for (let v = Math.ceil(xMin / step) * step; v <= xMax; v += step) ticks.push(v)
    return ticks.length ? ticks : [xMin]
  }, [xMin, xMax])

  const nearestX = (clientX: number) => {
    const rect = svgRef.current!.getBoundingClientRect()
    const px = ((clientX - rect.left) / rect.width) * width
    let best = xs[0]
    for (const x of xs) if (Math.abs(sx(x) - px) < Math.abs(sx(best) - px)) best = x
    return best
  }

  // pins survive re-renders but not a change of charted words: filter to
  // years that still exist on the x axis
  const pins = pinned.filter((x) => xs.includes(x))

  const entriesAt = (x: number) =>
    series
      .map((s) => ({ s, p: s.points.find((p) => p.x === x) }))
      .filter((e): e is { s: Series; p: Series['points'][number] } => !!e.p)

  const crosshair = (x: number) => (
    <g key={x}>
      <line x1={sx(x)} x2={sx(x)} y1={M.top} y2={M.top + ih} stroke="var(--color-ink-3)" strokeDasharray="3 3" />
      {entriesAt(x).map(({ s, p }) => (
        <circle key={s.name} cx={sx(p.x)} cy={sy(p.y)} r={4.5} fill={s.color} stroke="var(--color-paper)" strokeWidth={2} />
      ))}
    </g>
  )

  // pinned tooltips first (in pin order), live hover box last
  const boxes = [
    ...pins.map((x) => ({ x, isPin: true })),
    ...(hoverX !== null && !pins.includes(hoverX) ? [{ x: hoverX, isPin: false }] : []),
  ]

  // after each render, nudge any tooltip box that overlaps an earlier one
  // downward, so multiple pins (plus the live hover) all stay readable
  useLayoutEffect(() => {
    const els = [...(wrapRef.current?.querySelectorAll<HTMLElement>('[data-tip]') ?? [])]
    const placed: DOMRect[] = []
    for (const el of els) {
      el.style.top = '8px'
      for (let guard = 0; guard < els.length; guard++) {
        const r = el.getBoundingClientRect()
        const hit = placed.find(
          (p) => r.left < p.right + 6 && p.left < r.right + 6 && r.top < p.bottom + 6 && p.top < r.bottom,
        )
        if (!hit) break
        el.style.top = `${parseFloat(el.style.top) + (hit.bottom - r.top) + 6}px`
      }
      placed.push(el.getBoundingClientRect())
    }
  })

  return (
    // hover clears on leaving the wrapper (not the svg) so the mouse can
    // travel onto the tooltip box and click its movie link
    <div ref={wrapRef} className="relative" onMouseLeave={() => setHoverX(null)}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full cursor-crosshair select-none"
        role="img"
        aria-label={t('chart.axisAriaLabel', { yLabel })}
        onMouseMove={(e) => setHoverX(nearestX(e.clientX))}
        onClick={(e) => {
          const x = nearestX(e.clientX)
          setPinned((p) => togglePin(p.filter((v) => xs.includes(v)), x))
        }}
      >
        {yTicks.map((tick) => (
          <g key={tick}>
            <line x1={M.left} x2={width - M.right} y1={sy(tick)} y2={sy(tick)} stroke="var(--color-grid)" />
            <text x={M.left - 6} y={sy(tick) + 4} textAnchor="end" fontSize="11" fill="var(--color-ink-2)">
              {tick >= 1000 ? `${tick / 1000}k` : formatChartValue(tick)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <text key={tick} x={sx(tick)} y={height - 6} textAnchor="middle" fontSize="11" fill="var(--color-ink-2)">
            {tick}
          </text>
        ))}
        <line x1={M.left} x2={width - M.right} y1={M.top + ih} y2={M.top + ih} stroke="var(--color-ink)" strokeWidth={1.5} />
        {series.map((s) => (
          <polyline
            key={s.name}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')}
          />
        ))}
        {[...pins, ...(hoverX !== null && !pins.includes(hoverX) ? [hoverX] : [])].map(crosshair)}
      </svg>
      {boxes.map(({ x, isPin }) => {
        const entries = entriesAt(x)
        if (entries.length === 0) return null
        return (
          <div
            key={isPin ? `pin-${x}` : 'hover'}
            data-tip
            className={`absolute border-2 border-ink bg-card px-3 py-2 font-script text-xs shadow-[3px_3px_0_0_var(--color-ink)] ${
              isPin ? 'group pointer-events-auto' : 'pointer-events-none'
            }`}
            style={{ left: `${Math.min((sx(x) / width) * 100, 70)}%`, top: 8 }}
          >
            {isPin && (
              <button
                onClick={() => setPinned((p) => p.filter((v) => v !== x))}
                aria-label={t('chart.unpinAriaLabel', { year: x })}
                className="absolute -end-2 -top-2 hidden size-5 border-2 border-ink bg-card leading-none group-hover:block"
              >
                ✕
              </button>
            )}
            <div className="font-bold">{x}</div>
            {entries.map(({ s, p }) => (
              <div key={s.name} className="mt-0.5">
                <div className="flex items-center gap-1.5">
                  <span className="inline-block size-2.5 rounded-full" style={{ background: s.color }} />
                  <span>{s.name}</span>
                  <span className="ms-2 tabular-nums text-ink-2">{formatChartValue(p.y)}</span>
                </div>
                {p.note &&
                  (p.noteHref ? (
                    <a
                      href={p.noteHref}
                      className="pointer-events-auto ms-4 block max-w-52 truncate text-ink-3 underline hover:bg-mark"
                    >
                      {p.note}
                    </a>
                  ) : (
                    <div className="ms-4 max-w-52 truncate text-ink-3">{p.note}</div>
                  ))}
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}
