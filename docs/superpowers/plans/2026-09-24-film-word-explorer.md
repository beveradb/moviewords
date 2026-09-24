# Film Word Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An "Every word in this film" section on film pages: linkable word search (`#/movie/<id>?q=shit`) with stretched-spelling matches, a sortable paginated full word list, and "only in this film" words.

**Architecture:** A new pipeline stage bakes one sidecar per film, `json/words/<imdb_id>.json` = `{"w": [[word, count, films], ...]}`, streamed from `words_by_movie` like `stage_movies`. The app lazy-loads it (404-tolerant, like the blurb sidecar); all search/sort/paging logic is pure functions in `app/src/lib/wordExplorer.ts`; the UI is a self-contained `WordExplorer` component mounted in `Movie.tsx`.

**Tech Stack:** Python 3 + DuckDB (pytest via `uv`), React + TypeScript + vitest + @testing-library/react (jsdom), rclone -> R2, GitHub Actions auto-deploy.

Spec: `docs/superpowers/specs/2026-09-24-film-word-explorer-design.md` (deviation: the sidecars get the blurb sidecars' 1h Cache-Control, not `json/movie/**`'s 5 min - they only change on a rebake).

## Global Constraints

- Sidecar shape exactly `{"w": [[word, count, films], ...]}`, rows sorted by count desc then word asc; `films` = number of films in the whole corpus whose `words_by_movie` rows contain the word; every word of the film (no floor). Written compactly (`separators=(",", ":")`).
- Stretched spelling: `collapse(w)` squashes each run of one repeated character to a single char; a word `v` is a stretched variant of query `q` iff `v !== q`, `v` contains a run of 3+ identical characters, and `collapse(v) === collapse(q)`. ("shiiiit" matches "shit"; "good" does NOT match "god".)
- Only in this film: rows with `films === 1`, `count >= 2`, word made only of letters (`/^\p{L}+$/u`), by count desc, max 10.
- Full list: sort `count` (default: count desc, word asc) | `az` (word asc) | `rare` (films asc, count desc, word asc); 50 rows per page; a non-empty query filters the list by substring.
- `?q=` is read on load (and scrolls the section into view); typing updates the URL with `history.replaceState` (no new history entry).
- All UI copy in `app/src/messages/en.json` only via `t`/`n`/`tn`; never hand-edit the other 32 locale files (pre-commit hook translates; its glob misses `app/src/messages/.en-snapshot.json` - stage it manually if modified, then `npm run translate:validate`). Copy uses " - ", never em-dashes. `n()` for displayed numbers. `<option>` elements need explicit `value`.
- Data must be live on R2 before the app PR merges.
- Worktree `/Users/andrew/Projects/beveradb/moviewords-word-explorer` (branch `feat/film-word-explorer`); `pipeline/webdata` is an untracked symlink - never `git add -A`.
- Commit messages: subject, blank line, `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` (two `-m` flags).
- App checks: `cd app && npx tsc -b && npm run lint && npm test` (3 pre-existing LineChart rules-of-hooks lint errors are expected). Pipeline: `cd pipeline && uv run pytest -q`.

---

### Task 1: Pipeline - `words` stage + upload rule

**Files:**
- Modify: `pipeline/scripts/rebuild_web_data.py` (add `stage_words`, register `"words"`, docstring)
- Modify: `pipeline/scripts/upload_r2.sh` (add `all/json/words/**` next to the blurb rules)
- Test: `pipeline/tests/test_stage_words.py`

**Interfaces:**
- Produces: `OUT/json/words/<imdb_id>.json` per film; CLI `rebuild_web_data.py --corpus all --stage words`.

- [ ] **Step 1: Write the failing test** `pipeline/tests/test_stage_words.py`:

```python
import json

import duckdb

from scripts_path import add_scripts_to_path  # noqa: F401


def test_stage_words_writes_every_word_with_counts_and_film_frequency(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    wbm = tmp_path / "words_by_movie.parquet"
    duckdb.sql(f"""
        COPY (SELECT * FROM (VALUES
            ('tt1', 'shiiiit', 1), ('tt1', 'oh', 11), ('tt1', 'butch', 34), ('tt1', 'aa', 11),
            ('tt2', 'oh', 3), ('tt2', 'zed', 2))
            t(imdb_id, word, count)
            ORDER BY imdb_id, count DESC)
        TO '{wbm}' (FORMAT parquet)
    """)
    monkeypatch.setattr(rwd, "IN", tmp_path)
    monkeypatch.setattr(rwd, "OUT", tmp_path / "out")
    con = duckdb.connect()
    con.sql(f"CREATE VIEW words_by_movie AS SELECT * FROM '{wbm}'")
    rwd.stage_words(con)

    tt1 = json.loads((tmp_path / "out" / "json" / "words" / "tt1.json").read_text())
    # count desc, then word asc for ties; films = corpus document frequency
    assert tt1 == {"w": [["butch", 34, 1], ["aa", 11, 1], ["oh", 11, 2], ["shiiiit", 1, 1]]}
    tt2 = json.loads((tmp_path / "out" / "json" / "words" / "tt2.json").read_text())
    assert tt2 == {"w": [["oh", 3, 2], ["zed", 2, 1]]}
    assert "words" in rwd.STAGES
```

- [ ] **Step 2: Run to verify failure** - `cd pipeline && uv run pytest tests/test_stage_words.py -v` -> FAIL (`stage_words` missing).

- [ ] **Step 3: Implement** in `pipeline/scripts/rebuild_web_data.py`, after `stage_movies`:

```python
def stage_words(con):
    """json/words/<imdb_id>.json per film: EVERY word the film says as
    [word, count, films] (films = corpus document frequency), count desc then
    word - the film page's "Every word" explorer. Streams the (imdb_id,
    count DESC)-sorted words_by_movie like stage_movies (no per-film queries)."""
    films = dict(con.sql(
        "SELECT word, COUNT(*)::BIGINT FROM words_by_movie GROUP BY word").fetchall())
    out = OUT / "json" / "words"
    out.mkdir(parents=True, exist_ok=True)

    def flush(imdb_id, rows):
        rows.sort(key=lambda r: (-r[1], r[0]))
        payload = {"w": [[w, c, films[w]] for w, c in rows]}
        (out / f"{imdb_id}.json").write_text(json.dumps(payload, separators=(",", ":")))

    cur = con.execute(f"SELECT imdb_id, word, count FROM '{IN / 'words_by_movie.parquet'}'")
    current, rows, n = None, [], 0
    while batch := cur.fetchmany(1_000_000):
        for imdb_id, word, count in batch:
            if imdb_id != current:
                if current is not None:
                    flush(current, rows)
                    n += 1
                current, rows = imdb_id, []
            rows.append((word, int(count)))
    if current is not None:
        flush(current, rows)
        n += 1
    print(f"  wrote {n} word-list JSONs")
```

Register it: add `"words": stage_words` to `STAGES`. In the module docstring's stage list add:

```
  words       json/words/<id>.json per film (every word + corpus film count)
```

Note: `stage_words` must NOT run in the per-language/per-rating loops (per-film data is global). `bake_all_languages.py` iterates `rwd.STAGES` skipping only `"movies"` - add `"words"` to that skip (change `if name == "movies":` to `if name in ("movies", "words"):` and extend its comment). `bake_all_ratings.py` only runs `stage_trends` - no change.

- [ ] **Step 4: Upload rule** - in `pipeline/scripts/upload_r2.sh`, add `--filter '+ all/json/words/**'` to the first (1h) rclone command's blurb line and `--filter '- all/json/words/**'` to the second (5-min) command's blurb exclude line (keep them before the catch-alls).

- [ ] **Step 5: Run tests** - `cd pipeline && uv run pytest -q` -> all pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/rebuild_web_data.py pipeline/scripts/bake_all_languages.py pipeline/scripts/upload_r2.sh pipeline/tests/test_stage_words.py
git commit -m "feat(pipeline): bake per-film full word lists (json/words/<id>.json)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pure explorer logic + loader

**Files:**
- Create: `app/src/lib/wordExplorer.ts`, `app/src/lib/wordExplorer.test.ts`
- Modify: `app/src/lib/data.ts` (add `MovieWords`, `getMovieWords`)

**Interfaces:**
- Produces (exact):
  - `data.ts`: `export interface MovieWords { w: WordEntry[] }`, `export type WordEntry = [word: string, count: number, films: number]`, `export function getMovieWords(id: string): Promise<MovieWords | null>` (cached per URL; any non-OK or network error -> `null`).
  - `wordExplorer.ts`: `collapse(w: string): string`, `stretchedVariants(rows: WordEntry[], q: string): WordEntry[]`, `findWord(rows: WordEntry[], q: string): WordEntry | null`, `type SortKey = 'count' | 'az' | 'rare'`, `sortRows(rows: WordEntry[], key: SortKey): WordEntry[]`, `filterRows(rows: WordEntry[], q: string): WordEntry[]`, `PAGE_SIZE = 50`, `pageOf<T>(rows: T[], page: number): { rows: T[]; page: number; pages: number }` (page clamped to 1..pages, pages >= 1), `onlyInFilm(rows: WordEntry[]): WordEntry[]`, `movieWordsHash(id: string, q: string): string` (-> `#/movie/<id>` or `#/movie/<id>?q=<enc>`).

- [ ] **Step 1: Write failing tests** `app/src/lib/wordExplorer.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { WordEntry } from './data'
import {
  PAGE_SIZE, collapse, filterRows, findWord, movieWordsHash, onlyInFilm, pageOf, sortRows, stretchedVariants,
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
```

- [ ] **Step 2: Run to verify failure** - `cd app && npx vitest run src/lib/wordExplorer.test.ts` -> FAIL (module missing).

- [ ] **Step 3: Implement.** In `app/src/lib/data.ts`, after `getMovieBlurb`:

```ts
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
```

`app/src/lib/wordExplorer.ts`:

```ts
import type { WordEntry } from './data'

/** Pure logic for the film page's "Every word" explorer. */

const norm = (q: string) => q.trim().toLowerCase()

/** Squash every run of one repeated character to a single char. */
export const collapse = (w: string): string => w.replace(/(.)\1+/gu, '$1')

const hasRun3 = (w: string) => /(.)\1\1/u.test(w)

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
```

- [ ] **Step 4: Run tests** - `cd app && npx vitest run src/lib/wordExplorer.test.ts && npm test && npx tsc -b` -> pass.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/wordExplorer.ts app/src/lib/wordExplorer.test.ts app/src/lib/data.ts
git commit -m "feat(movie): word explorer logic + per-film word list loader" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `WordExplorer` component + film page wiring + copy

**Files:**
- Create: `app/src/components/WordExplorer.tsx`, `app/src/components/WordExplorer.test.tsx`
- Modify: `app/src/views/Movie.tsx` (mount it), `app/src/messages/en.json` (`movie.*` keys; locales regenerate via hook)

**Interfaces:**
- Consumes: Task 2's `getMovieWords`, `WordEntry`, and all `wordExplorer.ts` exports.
- Produces: `export function WordExplorer({ id, totalWords, initialQuery }: { id: string; totalWords: number; initialQuery: string })`.

- [ ] **Step 1: Copy** - add to the `"movie"` object in `app/src/messages/en.json` (after `"compareButton"`):

```json
    "everyWordHeading": "Every word in this film",
    "everyWordBody": "All {count} different words this film says, and how many films in the corpus say each one.",
    "findWordPlaceholder": "Find a word in this film…",
    "findWordAriaLabel": "Find a word in this film",
    "wordResult": "“{word}”: {count}× in this film · {rate}/1k words · said in {films} films",
    "wordNotSaid": "“{word}” isn't said in this film.",
    "alsoWrittenAs": "Also written as:",
    "wordTrendLink": "“{word}” over time →",
    "colWord": "Word",
    "colCount": "Count",
    "colPer1k": "Per 1k words",
    "colFilms": "Films that say it",
    "sortLabel": "Sort",
    "sortCount": "Most said",
    "sortAz": "A-Z",
    "sortRare": "Rarest",
    "prevPage": "← Prev",
    "nextPage": "Next →",
    "pageOf": "Page {page} of {pages}",
    "noWordMatches": "No words match “{q}”.",
    "onlyInFilmHeading": "Only in this film",
    "onlyInFilmBody": "Words no other film in the corpus says (said at least twice here).",
    "wordsUnavailable": "The full word list isn't available for this film.",
    "loadingWords": "Loading every word…",
```

- [ ] **Step 2: Write the failing component test** `app/src/components/WordExplorer.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import { WordExplorer } from './WordExplorer'

const data = { w: [['oh', 11, 40000], ['shoot', 6, 9000], ['sundance', 4, 1], ['shiiiit', 1, 12]] }

async function mount(initialQuery = '', body: unknown = data, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })))
  // the section is "seen" as soon as it's observed, so no-?q= mounts load too
  window.IntersectionObserver = class {
    constructor(private cb: IntersectionObserverCallback) {}
    observe() { this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver) }
    disconnect() {}
  } as unknown as typeof IntersectionObserver
  let view!: ReturnType<typeof render>
  await act(async () => {
    view = render(<I18nProvider><WordExplorer id={`tt${Math.random()}`} totalWords={6537} initialQuery={initialQuery} /></I18nProvider>)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
  return view
}

afterEach(() => vi.unstubAllGlobals())

describe('WordExplorer', () => {
  it('shows stretched spellings for a ?q= word the film never says straight', async () => {
    await mount('shit')
    expect(screen.getByText(/isn't said in this film/)).toBeTruthy()
    expect(screen.getByText(/Also written as/)).toBeTruthy()
    expect(screen.getAllByText('shiiiit').length).toBeGreaterThan(0)
  })

  it('shows the exact-match result line', async () => {
    await mount('oh')
    expect(screen.getByText(/“oh”: 11× in this film/)).toBeTruthy()
  })

  it('lists only-in-this-film words', async () => {
    await mount()
    expect(screen.getByText('Only in this film')).toBeTruthy()
  })

  it('updates the URL with replaceState as you type', async () => {
    const spy = vi.spyOn(window.history, 'replaceState')
    await mount()
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Find a word in this film'), { target: { value: 'shoot' } })
    })
    expect(spy).toHaveBeenLastCalledWith(null, '', expect.stringMatching(/#\/movie\/tt[\d.]+\?q=shoot$/))
  })

  it('says the list is unavailable on a 404', async () => {
    await mount('', 'nope', 404)
    expect(screen.getByText(/isn't available for this film/)).toBeTruthy()
  })
})
```

(`Only in this film` needs `films===1 && count>=2`: `sundance` qualifies.)

- [ ] **Step 3: Run to verify failure** - `cd app && npx vitest run src/components/WordExplorer.test.tsx` -> FAIL (module missing).

- [ ] **Step 4: Implement** `app/src/components/WordExplorer.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { getMovieWords, type MovieWords } from '../lib/data'
import { navigate } from '../lib/route'
import {
  filterRows, findWord, movieWordsHash, onlyInFilm, pageOf, sortRows, stretchedVariants, type SortKey,
} from '../lib/wordExplorer'
import { Spinner } from './ui'
import { useI18n } from '../i18n'

/** "Every word in this film": linkable word search (?q=) with stretched
 * spellings, a sortable/paginated full list, and only-in-this-film words.
 * Loads json/words/<id>.json lazily - when scrolled into view, or at once if
 * the page was opened with ?q=. */
export function WordExplorer({ id, totalWords, initialQuery }: { id: string; totalWords: number; initialQuery: string }) {
  const { t, n } = useI18n()
  const ref = useRef<HTMLElement>(null)
  const [wanted, setWanted] = useState(Boolean(initialQuery))
  const [data, setData] = useState<MovieWords | null | undefined>(undefined) // undefined = not loaded yet
  const [q, setQ] = useState(initialQuery)
  const [sort, setSort] = useState<SortKey>('count')
  const [page, setPage] = useState(1)

  // a linked ?q= jumps straight to the section; otherwise load on first sight
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (initialQuery) {
      el.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      return
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setWanted(true)
        io.disconnect()
      }
    })
    io.observe(el)
    return () => io.disconnect()
  }, [initialQuery])

  useEffect(() => {
    if (!wanted) return
    let cancelled = false
    getMovieWords(id).then((d) => !cancelled && setData(d))
    return () => {
      cancelled = true
    }
  }, [id, wanted])

  const rows = data?.w ?? []
  const exact = useMemo(() => findWord(rows, q), [rows, q])
  const variants = useMemo(() => stretchedVariants(rows, q), [rows, q])
  const listed = useMemo(() => sortRows(filterRows(rows, q), sort), [rows, q, sort])
  const paged = pageOf(listed, page)
  const unique = useMemo(() => onlyInFilm(rows), [rows])
  const per1k = (c: number) => n((c / Math.max(totalWords, 1)) * 1000, { maximumFractionDigits: 1 })
  const query = q.trim().toLowerCase()

  const onQuery = (value: string) => {
    setQ(value)
    setPage(1)
    window.history.replaceState(null, '', movieWordsHash(id, value))
  }

  return (
    <section ref={ref} className="mt-10 scroll-mt-4">
      <h2 className="slug text-sm">{t('movie.everyWordHeading')}</h2>
      {data === undefined && wanted && <Spinner label={t('movie.loadingWords')} />}
      {data === null && <p className="mt-2 font-script text-sm text-ink-2">{t('movie.wordsUnavailable')}</p>}
      {data && (
        <>
          <p className="mt-1 text-xs text-ink-2">{t('movie.everyWordBody', { count: n(rows.length) })}</p>
          <input
            value={q}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={t('movie.findWordPlaceholder')}
            aria-label={t('movie.findWordAriaLabel')}
            className="mt-3 w-72 max-w-full border-2 border-ink bg-card px-3 py-2 font-script placeholder:text-ink-3"
          />

          {query && (
            <div className="mt-3 border-l-2 border-ink-3 pl-4 font-script text-sm">
              {exact ? (
                <p>
                  {t('movie.wordResult', { word: exact[0], count: n(exact[1]), rate: per1k(exact[1]), films: n(exact[2]) })}
                </p>
              ) : (
                <p>{t('movie.wordNotSaid', { word: query })}</p>
              )}
              {variants.length > 0 && (
                <p className="mt-1">
                  {t('movie.alsoWrittenAs')}{' '}
                  {variants.map(([w, c]) => (
                    <span key={w} className="me-3 whitespace-nowrap">
                      <b>{w}</b> ×{n(c)}
                    </span>
                  ))}
                </p>
              )}
              <button className="mt-1 text-xs underline hover:bg-mark" onClick={() => navigate(`/trends?w=${encodeURIComponent(query)}`)}>
                {t('movie.wordTrendLink', { word: query })}
              </button>
            </div>
          )}

          {unique.length > 0 && !query && (
            <div className="mt-5">
              <h3 className="slug text-xs">{t('movie.onlyInFilmHeading')}</h3>
              <p className="mt-1 text-xs text-ink-2">{t('movie.onlyInFilmBody')}</p>
              <p className="mt-2 font-script text-sm">
                {unique.map(([w, c]) => (
                  <span key={w} className="me-3 whitespace-nowrap">{w} <span className="text-ink-2">×{n(c)}</span></span>
                ))}
              </p>
            </div>
          )}

          <div className="mt-5 flex items-center gap-2 font-script text-xs">
            <label className="flex items-center gap-1.5">
              {t('movie.sortLabel')}
              <select
                value={sort}
                onChange={(e) => { setSort(e.target.value as SortKey); setPage(1) }}
                className="border-2 border-ink bg-card px-1.5 py-1 font-script text-xs"
              >
                <option value="count">{t('movie.sortCount')}</option>
                <option value="az">{t('movie.sortAz')}</option>
                <option value="rare">{t('movie.sortRare')}</option>
              </select>
            </label>
          </div>

          {listed.length === 0 ? (
            <p className="mt-3 font-script text-sm text-ink-2">{t('movie.noWordMatches', { q: query })}</p>
          ) : (
            <table className="mt-3 w-full font-script text-sm">
              <thead>
                <tr className="border-b-2 border-ink text-start text-xs uppercase tracking-wide text-ink-2">
                  <th className="py-1 text-start">{t('movie.colWord')}</th>
                  <th className="py-1 text-end">{t('movie.colCount')}</th>
                  <th className="py-1 text-end">{t('movie.colPer1k')}</th>
                  <th className="py-1 text-end">{t('movie.colFilms')}</th>
                </tr>
              </thead>
              <tbody>
                {paged.rows.map(([w, c, f]) => (
                  <tr key={w} className="border-b border-paper-2">
                    <td className="py-1">
                      <button className="hover:bg-mark" onClick={() => navigate(`/trends?w=${encodeURIComponent(w)}`)}>{w}</button>
                    </td>
                    <td className="py-1 text-end tabular-nums">{n(c)}</td>
                    <td className="py-1 text-end tabular-nums text-ink-2">{per1k(c)}</td>
                    <td className="py-1 text-end tabular-nums text-ink-2">{n(f)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {paged.pages > 1 && (
            <div className="mt-3 flex items-center gap-3 font-script text-xs">
              <button disabled={paged.page <= 1} onClick={() => setPage(paged.page - 1)} className="border-2 border-ink px-2 py-1 disabled:opacity-40">
                {t('movie.prevPage')}
              </button>
              <span>{t('movie.pageOf', { page: n(paged.page), pages: n(paged.pages) })}</span>
              <button disabled={paged.page >= paged.pages} onClick={() => setPage(paged.page + 1)} className="border-2 border-ink px-2 py-1 disabled:opacity-40">
                {t('movie.nextPage')}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
```

In `app/src/views/Movie.tsx`: import `useRoute` from `../lib/route` and `WordExplorer` from `../components/WordExplorer`; in `MovieView` read `const { params } = useRoute()`; render, directly before the final "compare" button block:

```tsx
      <WordExplorer id={id} totalWords={movie.stats.total_words} initialQuery={params.get('q') ?? ''} />
```

(Check `MovieDetail`'s stats field name in `data.ts`; use it exactly. `key={id}` on `WordExplorer` so navigating between films resets its state.)

- [ ] **Step 5: Run tests** - `cd app && npx vitest run src/components/WordExplorer.test.tsx && npx tsc -b && npm run lint && npm test` -> pass (only the 3 pre-existing lint errors).

- [ ] **Step 6: Commit** (hook translates; stage `.en-snapshot.json` if modified and amend; then `npm run translate:validate`)

```bash
git add app/src/components/WordExplorer.tsx app/src/components/WordExplorer.test.tsx app/src/views/Movie.tsx app/src/messages/en.json
git commit -m "feat(movie): every-word explorer on film pages" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

(Controller does the browser check.)

---

### Task 4: Ops - bake + upload (controller)

- [ ] `cd pipeline && uv run python scripts/rebuild_web_data.py --corpus all --stage words` (inputs = the published 64.6k corpus via the `webdata` symlink); expect ~64.6k files in `webdata/out/all/json/words/`. Spot-check Butch Cassidy `tt0064115.json` contains `shiiiit` and 1,283 rows.
- [ ] rclone upload only `all/json/words/**` (`Cache-Control: public, max-age=3600`, `--transfers 32`); verify 200 + CORS for a few ids.

### Task 5: Ship (controller)

- [ ] Playwright on `localhost:5173`: `#/movie/tt0064115?q=shit` scrolls to the section and shows "isn't said" + "shiiiit ×1"; typing updates the URL without history entries; sort + paging; a film with no sidecar shows the unavailable note; 390px no overflow.
- [ ] Final whole-branch review; PR (no `@coderabbitai ignore`); squash-merge; deploy; prod check; draft the Butch Cassidy Reddit reply for the user.
