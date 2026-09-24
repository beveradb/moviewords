import { afterEach, describe, expect, it, vi } from 'vitest'
import { activeLanguages } from './languages'
import { q } from './duck'
import { bakedYearFilms, loadTrends, mergeTrendFiles } from './series'
import type { TrendFile } from './trends'

vi.mock('./languages', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./languages')>()),
  activeLanguages: vi.fn(() => []),
}))

vi.mock('./duck', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./duck')>()),
  q: vi.fn(async () => { throw new Error('engine should not be used') }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.mocked(activeLanguages).mockReturnValue([])
  vi.mocked(q).mockClear()
})

describe('mergeTrendFiles', () => {
  it('sums line counts exactly and unions top films', () => {
    const es: TrendFile = { line: [[2000, 5], [2001, 3]], top: [['tt_es', 'A', 2000, 5, 900]], byYear: [] }
    const fr: TrendFile = { line: [[2001, 4]], top: [['tt_fr', 'B', 2001, 4, 800]], byYear: [] }
    const out = mergeTrendFiles([es, fr])
    expect(out.line).toEqual([[2000, 5], [2001, 7]])
    expect(out.top.map((t) => t[0])).toEqual(['tt_es', 'tt_fr']) // count desc
  })
})

describe('bakedYearFilms', () => {
  it('reads the global file when no language filter is active', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ '2000': 3, '2001': 4 })))
    vi.stubGlobal('fetch', fetchMock)
    const m = await bakedYearFilms()
    expect([...m]).toEqual([[2000, 3], [2001, 4]])
    expect(String((fetchMock.mock.calls[0] as any[])[0])).toMatch(/\/all\/json\/year-films\.json$/)
  })

  it("sums the selected languages' files", async () => {
    vi.mocked(activeLanguages).mockReturnValue(['es', 'fr'])
    vi.stubGlobal('fetch', vi.fn(async (url: string) =>
      new Response(JSON.stringify(String(url).includes('/lang/es/') ? { '2000': 2 } : { '2000': 5, '2001': 1 })),
    ))
    const m = await bakedYearFilms()
    expect([...m].sort((a, b) => a[0] - b[0])).toEqual([[2000, 7], [2001, 1]])
  })
})

describe('rating-scoped loaders', () => {
  const byUrl = (map: Record<string, unknown>) =>
    vi.fn(async (url: string) => {
      const hit = Object.entries(map).find(([k]) => String(url).endsWith(k))
      return hit ? new Response(JSON.stringify(hit[1])) : new Response('nope', { status: 404 })
    })

  it('reads year-films from the rating slice', async () => {
    const f = byUrl({ '/all/rating/pg/json/year-films.json': { '1990': 4 } })
    vi.stubGlobal('fetch', f)
    expect([...(await bakedYearFilms('pg'))]).toEqual([[1990, 4]])
    expect(String(f.mock.calls[0][0])).toMatch(/\/all\/rating\/pg\/json\/year-films\.json$/)
  })

  it('reads trend + totals from the rating slice and drops pre-1968 years', async () => {
    vi.stubGlobal('fetch', byUrl({
      '/all/rating/r/json/year-totals.json': { '1960': 500_000, '1970': 500_000 },
      '/all/rating/r/json/trend/fuck.json': { line: [[1960, 5], [1970, 7]], top: [], byYear: [] },
    }))
    const { wordSeries, baked } = await loadTrends(['fuck'], ['c1'], 'r')
    expect(baked).toBe(true)
    expect(wordSeries.series[0].points.map((p) => p.x)).toEqual([1970])
    expect(wordSeries.plottedYears).toEqual([1970])
  })

  it('does not fall back to the SQL engine for a rated view', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })))
    await expect(loadTrends(['fuck'], ['c1'], 'g')).rejects.toThrow(/500/)
    expect(vi.mocked(q)).not.toHaveBeenCalled()
  })
})
