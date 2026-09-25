import { activeLanguages } from './languages'
import {
  mergeLeaderboard, mergeSignatures, mergeShifts, mergeSuperlatives,
  mergeWonders, mergeUbiquity,
} from './merge'

export const DATA_BASE =
  import.meta.env.VITE_DATA_BASE ?? 'https://data.moviewords.org'

/** The unfiltered corpus tree (also the base for per-language slices). */
export const globalUrl = (path: string) => `${DATA_BASE}/all/${path}`
export const langUrl = (code: string, path: string) => `${DATA_BASE}/all/lang/${code}/${path}`

/** A per-MPAA-rating slice (Trends only): all/rating/<code>/... */
export const ratingUrl = (code: string, path: string) => `${DATA_BASE}/all/rating/${code}/${path}`

// Back-compat shim for callers still importing dataUrl (movie/index/wordlists,
// duck.ts parquet reads): the global all/ tree.
export const dataUrl = (path: string) => globalUrl(path)

export interface MovieIndexEntry {
  id: string
  title: string
  year: number
  rating: number
  votes: number
  total_words: number
  unique_words: number
  genres: string[]
  /** ISO 639-1 original language - present in indexes built after 2026-09-14 */
  lang?: string
  /** "low": the film's only subtitle is low quality (machine-translated,
   * auto-captions, possibly another film). Searchable and has a page, but
   * is in no total, chart or ranking - skip it when counting films. */
  q?: 'low'
}

/** Whether an index entry counts toward the corpus (totals, charts, lists). */
export const inCorpus = (m: MovieIndexEntry) => !m.q

export type QualityFlag = 'asr' | 'machine-translated' | 'wrong-cast'

export interface MovieDetail {
  imdb_id: string
  title: string
  year: number
  original_language?: string
  stats: { total_words: number; unique_words: number; words_per_minute: number | null }
  top: [string, number][]
  top_all: [string, number][]
  distinctive: [string, number][]
  /** Present only for films left out of the aggregates (see MovieIndexEntry.q). */
  quality?: { tier: 'low'; flags: QualityFlag[] }
}

export interface MovieBlurb {
  overview?: string
  tagline?: string
  runtime?: number
}

export interface Leaderboard {
  words: [string, number, number, ...unknown[]][]
  stopwords: [string, number, number, ...unknown[]][]
}

export interface Wordlists {
  stopwords: string[]
  profanity: string[]
}

// caches the in-flight promise, not the value, so concurrent callers (e.g.
// three compare cards mounting together) share one download of movies-index
const cache = new Map<string, Promise<unknown>>()

function fetchOne<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    const p = fetch(url).then((res) => {
      if (!res.ok) throw new Error(`${res.status} fetching ${url}`)
      return res.json()
    })
    p.catch(() => cache.delete(url))
    cache.set(url, p)
  }
  return cache.get(url) as Promise<T>
}

export function fetchJSON<T>(path: string): Promise<T> {
  return fetchOne<T>(globalUrl(path))
}

/** Language-aware aggregate fetch. 0 languages -> the global all/ file; 1 -> that
 * slice (exact); 2+ -> fetch every selected slice and merge. */
export function fetchLangMerged<T>(path: string, merge: (parts: T[]) => T): Promise<T> {
  const langs = activeLanguages()
  if (langs.length === 0) return fetchOne<T>(globalUrl(path))
  return Promise.all(langs.map((c) => fetchOne<T>(langUrl(c, path)))).then((parts) =>
    parts.length === 1 ? parts[0] : merge(parts),
  )
}

export interface SignatureEntry {
  movie_count: number
  total_words: number
  top: [string, number][]
  signature: [string, number][]
  /** v2 fields (extended signatures) — absent on older cached JSON. */
  swears_per_1k?: number
  unique_words?: number
  top_words?: [string, number][]
}

export interface ShiftRow {
  word: string
  score: number
  rates: [number, number][]
}

export interface Shifts {
  decades: number[]
  risers: ShiftRow[]
  fallers: ShiftRow[]
}

export interface FilmSuperlative {
  id: string
  title: string
  year: number
  value: number
}

export interface Superlatives {
  chattiest: FilmSuperlative[]
  vocabulary: FilmSuperlative[]
  sweariest: FilmSuperlative[]
  repetitive: FilmSuperlative[]
}

export interface WonderRow {
  word: string
  id: string
  title: string
  year: number
  count: number
  total: number
  share: number
}

export interface UbiquityRow {
  word: string
  films: number
  share: number
}

export const getShifts = () => fetchLangMerged<Shifts>('json/leaderboards/shifts.json', mergeShifts)
export const getSuperlatives = () => fetchLangMerged<Superlatives>('json/leaderboards/films.json', mergeSuperlatives)
export const getWonders = () => fetchLangMerged<WonderRow[]>('json/leaderboards/wonders.json', mergeWonders)
export const getUbiquity = () => fetchLangMerged<UbiquityRow[]>('json/leaderboards/everywhere.json', mergeUbiquity)
export const getSignatures = (kind: 'decades' | 'genres') =>
  fetchLangMerged<Record<string, SignatureEntry>>(`json/signature/${kind}.json`, mergeSignatures)
export const getLeaderboard = () => fetchLangMerged<Leaderboard>('json/leaderboard-default.json', mergeLeaderboard)

// global (never per-language):
export const getMovieIndex = () => fetchJSON<MovieIndexEntry[]>('json/movies-index.json')
export const getMovie = (id: string) => fetchJSON<MovieDetail>(`json/movie/${id}.json`)
export const getWordlists = () => fetchJSON<Wordlists>('json/wordlists.json')

// Own in-flight cache (not fetchOne): a missing sidecar (404) must resolve to
// null and be cached as such, not treated as an error to retry/delete.
const blurbCache = new Map<string, Promise<MovieBlurb | null>>()

/** Lazy, 404-tolerant blurb sidecar. Missing file -> null (page renders fine). */
export function getMovieBlurb(id: string): Promise<MovieBlurb | null> {
  const url = globalUrl(`json/blurb/${id}.json`)
  if (!blurbCache.has(url)) {
    blurbCache.set(
      url,
      fetch(url)
        .then((res) => (res.ok ? (res.json() as Promise<MovieBlurb>) : null))
        .catch(() => null),
    )
  }
  return blurbCache.get(url) as Promise<MovieBlurb | null>
}

/** [word, count in this film, films in the corpus that say it] */
export type WordEntry = [word: string, count: number, films: number]

/** Every word a film says - json/words/<id>.json, the film page explorer. */
export interface MovieWords {
  w: WordEntry[]
}

const wordsCache = new Map<string, Promise<MovieWords | null>>()

/** A film's full word list, or null when it isn't baked (404) or the fetch
 * fails - the explorer section then says so; the rest of the page is fine. */
export function getMovieWords(id: string): Promise<MovieWords | null> {
  const url = globalUrl(`json/words/${id}.json`)
  if (!wordsCache.has(url)) {
    wordsCache.set(
      url,
      fetch(url)
        .then((res) => (res.ok ? (res.json() as Promise<MovieWords>) : null))
        .catch(() => null),
    )
  }
  return wordsCache.get(url) as Promise<MovieWords | null>
}

/** The corpus's films (no low-quality entries - see inCorpus), filtered to
 * the active language selection (empty = all). */
export async function getFilteredMovieIndex(): Promise<MovieIndexEntry[]> {
  const [idx, langs] = [(await getMovieIndex()).filter(inCorpus), activeLanguages()]
  if (langs.length === 0) return idx
  const set = new Set(langs.includes('zh') ? [...langs, 'cn'] : langs)
  return idx.filter((m) => m.lang != null && set.has(m.lang))
}
