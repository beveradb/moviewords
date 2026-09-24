import { describe, expect, it } from 'vitest'
import type { WordEntry } from './data'
import {
  PAGE_SIZE, collapse, filterRows, findWord, formatPer1k, listFor, movieWordsHash, onlyInFilm, pageOf, sortRows,
  stretchedVariants,
} from './wordExplorer'

const rows: WordEntry[] = [
  ['oh', 11, 40000], ['shoot', 6, 9000], ['shiiiit', 1, 12], ['shiiiitttt', 2, 3],
  ['good', 5, 50000], ['god', 3, 45000], ['sundance', 4, 1], ['kid', 4, 30000],
  ['xq9', 3, 1], ['zzz', 2, 1], ['bolivia', 1, 1],
]

describe('collapse', () => {
  it('squashes runs of a repeated character', () => {
    expect(collapse('shiiiitttt')).toBe('shit')
    expect(collapse('good')).toBe('god')
    expect(collapse('oh')).toBe('oh')
  })
  it('leaves digit runs alone (letters only)', () => {
    expect(collapse('1000')).toBe('1000')
  })
})

describe('stretchedVariants', () => {
  it('finds stretched spellings of the query', () => {
    expect(stretchedVariants(rows, 'shit').map((r) => r[0])).toEqual(['shiiiit', 'shiiiitttt'])
  })
  it('needs a 3+ run, so god does not match good', () => {
    expect(stretchedVariants(rows, 'god')).toEqual([])
  })
  it('never returns the query itself and is case/space-insensitive', () => {
    expect(stretchedVariants(rows, ' SHIIIIT ').map((r) => r[0])).toEqual(['shiiiitttt'])
  })
  it('does not treat a digit run as a stretched spelling', () => {
    expect(stretchedVariants([['1000', 1, 1], ['10', 2, 5]], '10')).toEqual([])
  })
})

describe('findWord', () => {
  it('finds the exact word, normalised', () => {
    expect(findWord(rows, ' Oh ')).toEqual(['oh', 11, 40000])
    expect(findWord(rows, 'shit')).toBeNull()
  })
})

describe('sortRows', () => {
  it('sorts by count desc then word', () => {
    expect(sortRows(rows, 'count').slice(0, 4).map((r) => r[0])).toEqual(['oh', 'shoot', 'good', 'kid'])
  })
  it('sorts A-Z', () => {
    expect(sortRows(rows, 'az')[0][0]).toBe('bolivia')
  })
  it('sorts rarest first, then count desc', () => {
    expect(sortRows(rows, 'rare').slice(0, 4).map((r) => r[0])).toEqual(['sundance', 'xq9', 'zzz', 'bolivia'])
  })
  it('does not mutate its input', () => {
    const copy = [...rows]
    sortRows(rows, 'az')
    expect(rows).toEqual(copy)
  })
})

describe('filterRows', () => {
  it('filters by substring; empty query keeps all', () => {
    expect(filterRows(rows, 'shi').map((r) => r[0])).toEqual(['shiiiit', 'shiiiitttt'])
    expect(filterRows(rows, '  ')).toHaveLength(rows.length)
  })
})

describe('listFor', () => {
  it('includes stretched variants alongside substring matches, no duplicates', () => {
    const words = listFor(rows, 'shit').map((r) => r[0])
    expect(words.filter((w) => w === 'shiiiit')).toHaveLength(1)
    expect(words.filter((w) => w === 'shiiiitttt')).toHaveLength(1)
  })
  it('is just the substring match when there are no stretched variants', () => {
    expect(listFor(rows, 'sho').map((r) => r[0])).toEqual(['shoot'])
  })
  it('returns all rows for an empty query', () => {
    expect(listFor(rows, '')).toEqual(rows)
  })
})

describe('formatPer1k', () => {
  const n = (v: number, o?: Intl.NumberFormatOptions) => new Intl.NumberFormat('en', o).format(v)
  it('shows "<0.1" for tiny non-zero rates instead of rounding to 0', () => {
    expect(formatPer1k(1, 22000, n)).toBe('<0.1')
  })
  it('formats ordinary rates to one decimal', () => {
    expect(formatPer1k(147, 22600, n)).toBe('6.5')
  })
  it('shows plain 0 for a zero count', () => {
    expect(formatPer1k(0, 1000, n)).toBe('0')
  })
})

describe('pageOf', () => {
  const many = Array.from({ length: 120 }, (_, i) => i)
  it('slices pages of PAGE_SIZE and clamps the page', () => {
    expect(PAGE_SIZE).toBe(50)
    expect(pageOf(many, 1)).toMatchObject({ page: 1, pages: 3 })
    expect(pageOf(many, 3).rows).toHaveLength(20)
    expect(pageOf(many, 99).page).toBe(3)
    expect(pageOf(many, 0).page).toBe(1)
    expect(pageOf([], 1)).toEqual({ rows: [], page: 1, pages: 1 })
  })
})

describe('onlyInFilm', () => {
  it('keeps letter-only words said 2+ times that no other film says', () => {
    expect(onlyInFilm(rows).map((r) => r[0])).toEqual(['sundance', 'zzz'])
  })
})

describe('movieWordsHash', () => {
  it('adds an encoded ?q= only when there is a query', () => {
    expect(movieWordsHash('tt0064115', 'shit')).toBe('#/movie/tt0064115?q=shit')
    expect(movieWordsHash('tt0064115', "don't")).toBe(`#/movie/tt0064115?q=${encodeURIComponent("don't")}`)
    expect(movieWordsHash('tt0064115', '  ')).toBe('#/movie/tt0064115')
  })
})
