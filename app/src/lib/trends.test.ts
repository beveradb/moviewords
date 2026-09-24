import { describe, expect, it } from 'vitest'
import {
  MIN_YEAR_WORDS,
  type TrendFile,
  formatYearRanges,
  groupTopMovies,
  togglePin,
  topMovieRows,
  toSeries,
  trendByYear,
  trendTopFilms,
  trendYearRows,
  wordKey,
  perFilmSeries,
  perFilmSummary,
  trendsHref,
  isPerFilm,
  formatPerFilm,
  RATINGS,
  RATING_MIN_YEAR,
  ratingFromParams,
  ratingLabel,
  filmsSince,
} from './trends'

describe('formatYearRanges', () => {
  it('collapses consecutive years into en-dash ranges', () => {
    expect(formatYearRanges([1916, 1922, 1923, 1925, 1927, 1928, 1929, 2024])).toBe(
      '1916, 1922–1923, 1925, 1927–1929, 2024',
    )
  })

  it('handles a single year', () => {
    expect(formatYearRanges([1935])).toBe('1935')
  })

  it('handles one contiguous run', () => {
    expect(formatYearRanges([1914, 1915, 1916])).toBe('1914–1916')
  })

  it('returns empty string for no years', () => {
    expect(formatYearRanges([])).toBe('')
  })
})

describe('groupTopMovies', () => {
  it('groups flat query rows by word, then year', () => {
    const grouped = groupTopMovies([
      { word: 'sword', year: 1935, imdb_id: 'tt1', title: 'Captain Blood', count: 23 },
      { word: 'sword', year: 1938, imdb_id: 'tt2', title: 'Robin Hood', count: 30 },
      { word: 'gun', year: 1935, imdb_id: 'tt3', title: 'G Men', count: 40 },
    ])
    expect([...grouped.keys()]).toEqual(['sword', 'gun'])
    expect(grouped.get('sword')?.get(1935)).toEqual({ imdb_id: 'tt1', title: 'Captain Blood', count: 23 })
    expect(grouped.get('sword')?.get(1938)?.title).toBe('Robin Hood')
    expect(grouped.get('gun')?.get(1938)).toBeUndefined()
  })

  it('returns an empty map for no rows', () => {
    expect(groupTopMovies([]).size).toBe(0)
  })
})

describe('topMovieRows', () => {
  const byYear = new Map([
    [1935, { imdb_id: 'tt1', title: 'Captain Blood', count: 23 }],
    [1937, { imdb_id: 'tt2', title: 'The Prisoner of Zenda', count: 12 }],
  ])

  it('emits one row per plotted year, ascending, with null gaps', () => {
    expect(topMovieRows([1937, 1935, 1936], byYear)).toEqual([
      { year: 1935, movie: { imdb_id: 'tt1', title: 'Captain Blood', count: 23 } },
      { year: 1936, movie: null },
      { year: 1937, movie: { imdb_id: 'tt2', title: 'The Prisoner of Zenda', count: 12 } },
    ])
  })

  it('handles a word with no data at all', () => {
    expect(topMovieRows([1935, 1936], undefined)).toEqual([
      { year: 1935, movie: null },
      { year: 1936, movie: null },
    ])
  })

  it('returns no rows for no years', () => {
    expect(topMovieRows([], byYear)).toEqual([])
  })
})

describe('togglePin', () => {
  it('adds an unpinned year', () => {
    expect(togglePin([1935], 1985)).toEqual([1935, 1985])
  })

  it('removes an already-pinned year', () => {
    expect(togglePin([1935, 1985], 1935)).toEqual([1985])
  })

  it('drops the oldest pin when a 4th is added', () => {
    expect(togglePin([1935, 1960, 1985], 2001)).toEqual([1960, 1985, 2001])
  })

  it('pins the first year on an empty list', () => {
    expect(togglePin([], 1935)).toEqual([1935])
  })
})

describe('MIN_YEAR_WORDS', () => {
  it('sits between the thin silent-era years and the first solid talkie year', () => {
    // 1929 has ~66k corpus words (10 films), 1930 has ~126k (18 films):
    // the floor must separate them or the trim stops doing its job
    expect(MIN_YEAR_WORDS).toBeGreaterThan(66_000)
    expect(MIN_YEAR_WORDS).toBeLessThanOrEqual(126_000)
  })
})

describe('toSeries', () => {
  const totals = new Map([
    [1980, 200_000],
    [1981, 50_000], // below MIN_YEAR_WORDS floor
    [1982, 300_000],
  ])
  const rows = [
    { word: 'love', year: 1980, count: 100 },
    { word: 'love', year: 1981, count: 999 }, // dropped: year below floor
    { word: 'love', year: 1982, count: 300 },
    { word: 'war', year: 1980, count: 50 },
  ]

  it('reports years dropped for being below the corpus-size floor', () => {
    expect(toSeries(rows, totals, ['love', 'war'], ['c1', 'c2']).trimmedYears).toBe('1981')
  })

  it('builds per-million-words series with post-filter colors', () => {
    expect(toSeries(rows, totals, ['love', 'war'], ['c1', 'c2']).series).toEqual([
      {
        name: 'love',
        color: 'c1',
        points: [
          { x: 1980, y: (100 / 200_000) * 1_000_000 },
          { x: 1982, y: (300 / 300_000) * 1_000_000 },
        ],
      },
      { name: 'war', color: 'c2', points: [{ x: 1980, y: (50 / 200_000) * 1_000_000 }] },
    ])
  })

  it('lists plotted years across the kept range, floor gaps excluded', () => {
    expect(toSeries(rows, totals, ['love'], ['c1']).plottedYears).toEqual([1980, 1982])
  })

  it('reports words with no kept data as missing', () => {
    expect(toSeries(rows, totals, ['love', 'ghost'], ['c1', 'c2']).missing).toEqual(['ghost'])
  })
})

describe('wordKey', () => {
  it('leaves RFC3986-unreserved characters literal', () => {
    expect(wordKey('love')).toBe('love')
    expect(wordKey('re-do_now.v2~')).toBe('re-do_now.v2~')
  })

  it("percent-encodes apostrophes so contractions do not 404 (must match Python quote)", () => {
    // encodeURIComponent alone leaves ' literal; Python quote(safe='') encodes it
    expect(wordKey("don't")).toBe('don%27t')
  })

  it('encodes the other sub-delims encodeURIComponent skips', () => {
    expect(wordKey('a!b(c)*d')).toBe('a%21b%28c%29%2Ad')
  })

  it('percent-encodes spaces, slashes and non-ASCII as UTF-8 uppercase hex', () => {
    expect(wordKey('rock and roll')).toBe('rock%20and%20roll')
    expect(wordKey('a/b')).toBe('a%2Fb')
    expect(wordKey('café')).toBe('caf%C3%A9')
  })
})

describe('trend file transforms', () => {
  const file: TrendFile = {
    line: [
      [1978, 78],
      [2001, 104],
    ],
    top: [
      ['tt0120737', 'The Fellowship of the Ring', 2001, 104, 20000],
      ['tt0077869', 'The Lord of the Rings', 1978, 78, 15000],
    ],
    byYear: [
      [1978, 'tt0077869', 'The Lord of the Rings', 78],
      [2001, 'tt0120737', 'The Fellowship of the Ring', 104],
    ],
  }

  it('trendYearRows tags line points with the word', () => {
    expect(trendYearRows('ring', file)).toEqual([
      { word: 'ring', year: 1978, count: 78 },
      { word: 'ring', year: 2001, count: 104 },
    ])
  })

  it('trendTopFilms expands the compact tuples into objects', () => {
    expect(trendTopFilms(file)[0]).toEqual({
      imdb_id: 'tt0120737',
      title: 'The Fellowship of the Ring',
      year: 2001,
      count: 104,
      total_words: 20000,
    })
  })

  it('trendByYear keys the top movie by year', () => {
    const m = trendByYear(file)
    expect(m.get(2001)).toEqual({ imdb_id: 'tt0120737', title: 'The Fellowship of the Ring', count: 104 })
    expect(m.get(1999)).toBeUndefined()
  })
})

describe('toSeries raw data', () => {
  it('keeps the kept rows and totals for re-dividing', () => {
    const totals = new Map([[1980, 200_000], [1981, 50_000]])
    const rows = [
      { word: 'love', year: 1980, count: 100 },
      { word: 'love', year: 1981, count: 9 },
    ]
    const ws = toSeries(rows, totals, ['love'], ['c1'])
    expect(ws.rows).toEqual([{ word: 'love', year: 1980, count: 100 }])
    expect(ws.totals).toBe(totals)
  })
})

describe('perFilmSeries', () => {
  const totals = new Map([[1980, 200_000], [1981, 50_000], [1982, 300_000]])
  const rows = [
    { word: 'love', year: 1980, count: 100 },
    { word: 'love', year: 1981, count: 999 }, // trimmed year stays trimmed
    { word: 'love', year: 1982, count: 300 },
    { word: 'war', year: 1980, count: 50 },
  ]
  const ws = toSeries(rows, totals, ['love', 'war'], ['c1', 'c2'])

  it('divides counts by films released that year', () => {
    const films = new Map([[1980, 10], [1981, 1], [1982, 20]])
    expect(perFilmSeries(ws, films)).toEqual([
      { name: 'love', color: 'c1', points: [{ x: 1980, y: 10 }, { x: 1982, y: 15 }] },
      { name: 'war', color: 'c2', points: [{ x: 1980, y: 5 }] },
    ])
  })

  it('drops points for years with no film count', () => {
    const films = new Map([[1980, 10]])
    expect(perFilmSeries(ws, films)[0].points).toEqual([{ x: 1980, y: 10 }])
  })

  it('keeps chart notes on points', () => {
    const noted = { ...ws, series: [{ ...ws.series[0], points: [{ x: 1980, y: 500, note: 'Film', noteHref: '#/movie/tt1' }] }] }
    expect(perFilmSeries(noted, new Map([[1980, 10]]))[0].points[0]).toEqual(
      { x: 1980, y: 10, note: 'Film', noteHref: '#/movie/tt1' },
    )
  })
})

describe('perFilmSummary', () => {
  const totals = new Map([[2009, 200_000], [2010, 200_000], [2011, 200_000]])
  const rows = [
    { word: 'dude', year: 2009, count: 30 },
    { word: 'dude', year: 2011, count: 90 },
  ]
  const ws = toSeries(rows, totals, ['dude'], ['c1'])
  const films = new Map([[2009, 10], [2010, 10], [2011, 20]])

  it('averages the latest plotted decade and all plotted years (absent years count as 0)', () => {
    // 2010s: (0 + 90) / (10 + 20) = 3; all: (30 + 0 + 90) / 40 = 3
    expect(perFilmSummary(ws, films, 'dude')).toEqual({ decade: 2010, latest: 3, overall: 3 })
  })

  it('is null for a word with no data', () => {
    expect(perFilmSummary(ws, films, 'nope')).toBeNull()
  })
})

describe('trendsHref / isPerFilm', () => {
  it('builds a linkable URL, adding per=film and rating only when set', () => {
    expect(trendsHref(['fuck', "don't"])).toBe(`/trends?w=${encodeURIComponent("fuck,don't")}`)
    expect(trendsHref(['fuck'], { perFilm: true })).toBe('/trends?w=fuck&per=film')
    expect(trendsHref(['fuck'], { rating: 'pg13' })).toBe('/trends?w=fuck&rating=pg13')
    expect(trendsHref(['fuck'], { perFilm: true, rating: 'r' })).toBe('/trends?w=fuck&per=film&rating=r')
    expect(trendsHref(['fuck'], { perFilm: false, rating: null })).toBe('/trends?w=fuck')
  })
  it('reads the per param', () => {
    expect(isPerFilm(new URLSearchParams('w=a&per=film'))).toBe(true)
    expect(isPerFilm(new URLSearchParams('w=a'))).toBe(false)
  })
})

describe('ratings', () => {
  it('lists the four MPAA buckets in order with display labels', () => {
    expect(RATINGS.map((r) => r.code)).toEqual(['g', 'pg', 'pg13', 'r'])
    expect(ratingLabel('pg13')).toBe('PG-13')
    expect(ratingLabel('r')).toBe('R & NC-17/X')
    expect(RATING_MIN_YEAR).toBe(1968)
  })
  it('accepts only known rating codes from the URL', () => {
    expect(ratingFromParams(new URLSearchParams('rating=pg'))).toBe('pg')
    expect(ratingFromParams(new URLSearchParams('rating=PG'))).toBeNull()
    expect(ratingFromParams(new URLSearchParams('rating=xxx'))).toBeNull()
    expect(ratingFromParams(new URLSearchParams('rating=nc17'))).toBeNull()
    expect(ratingFromParams(new URLSearchParams(''))).toBeNull()
  })
  it('counts films released from a year onwards', () => {
    expect(filmsSince(new Map([[1960, 5], [1968, 2], [1990, 3]]), 1968)).toBe(5)
  })
})

describe('formatPerFilm', () => {
  const n = (v: number, o?: Intl.NumberFormatOptions) => new Intl.NumberFormat('en', o).format(v)
  it('uses 1 decimal from 1 up, 2 below, "<0.01" for tiny, "0" for zero', () => {
    expect(formatPerFilm(10.46, n)).toBe('10.5')
    expect(formatPerFilm(0.054, n)).toBe('0.05')
    expect(formatPerFilm(0.004, n)).toBe('<0.01')
    expect(formatPerFilm(0, n)).toBe('0')
  })
})
