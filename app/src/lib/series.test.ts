import { afterEach, describe, expect, it, vi } from 'vitest'
import { activeLanguages } from './languages'
import { bakedYearFilms, mergeTrendFiles } from './series'
import type { TrendFile } from './trends'

vi.mock('./languages', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./languages')>()),
  activeLanguages: vi.fn(() => []),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.mocked(activeLanguages).mockReturnValue([])
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
