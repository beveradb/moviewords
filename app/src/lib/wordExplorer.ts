import type { WordEntry } from './data'

/** Pure logic for the film page's "Every word" explorer. */

const norm = (q: string) => q.trim().toLowerCase()

/** Squash every run of one repeated letter to a single char (letters only, so
 * digit/punctuation runs like "1000" aren't treated as stretched spellings). */
export const collapse = (w: string): string => w.replace(/(\p{L})\1+/gu, '$1')

const hasRun3 = (w: string) => /(\p{L})\1\1/u.test(w)

/** Stretched spellings of `q` said in this film ("shiiiit" for "shit"): a 3+
 * run of one letter that collapses to the same word. The 3-run rule keeps
 * ordinary doubles apart ("good" is not "god"). */
export function stretchedVariants(rows: WordEntry[], q: string): WordEntry[] {
  const query = norm(q)
  if (!query) return []
  const target = collapse(query)
  return rows.filter(([w]) => w !== query && hasRun3(w) && collapse(w) === target)
}

export function findWord(rows: WordEntry[], q: string): WordEntry | null {
  const query = norm(q)
  return rows.find(([w]) => w === query) ?? null
}

export type SortKey = 'count' | 'az' | 'rare'

const byWord = (a: WordEntry, b: WordEntry) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)

export function sortRows(rows: WordEntry[], key: SortKey): WordEntry[] {
  const out = [...rows]
  if (key === 'az') return out.sort(byWord)
  if (key === 'rare') return out.sort((a, b) => a[2] - b[2] || b[1] - a[1] || byWord(a, b))
  return out.sort((a, b) => b[1] - a[1] || byWord(a, b))
}

export function filterRows(rows: WordEntry[], q: string): WordEntry[] {
  const query = norm(q)
  return query ? rows.filter(([w]) => w.includes(query)) : rows
}

/** Full-list rows for a query: substring matches plus any stretched
 * spellings not already included, so "shit" also lists "shiiiit". */
export function listFor(rows: WordEntry[], q: string): WordEntry[] {
  const matches = filterRows(rows, q)
  const extra = stretchedVariants(rows, q).filter((row) => !matches.includes(row))
  return [...matches, ...extra]
}

/** Readable per-1k-words rate: never renders a said-once word as "0". */
export function formatPer1k(
  count: number,
  totalWords: number,
  n: (v: number, o?: Intl.NumberFormatOptions) => string,
): string {
  const rate = (count / Math.max(totalWords, 1)) * 1000
  if (rate === 0) return n(0)
  if (rate < 0.1) return `<${n(0.1, { minimumFractionDigits: 1 })}`
  return n(rate, { maximumFractionDigits: 1 })
}

export const PAGE_SIZE = 50

export function pageOf<T>(rows: T[], page: number): { rows: T[]; page: number; pages: number } {
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const p = Math.min(Math.max(1, page), pages)
  return { rows: rows.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE), page: p, pages }
}

/** Words no other film in the corpus says, said 2+ times here, letters only
 * (drops one-off typos / fragments), most-said first. */
export const onlyInFilm = (rows: WordEntry[]): WordEntry[] =>
  sortRows(rows.filter(([w, c, f]) => f === 1 && c >= 2 && /^\p{L}+$/u.test(w)), 'count').slice(0, 10)

export const movieWordsHash = (id: string, q: string): string =>
  norm(q) ? `#/movie/${id}?q=${encodeURIComponent(norm(q))}` : `#/movie/${id}`
