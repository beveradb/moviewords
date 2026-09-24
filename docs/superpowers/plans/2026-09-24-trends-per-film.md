# Trends "per film" view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Trends page show any word's average uses **per film** (toggle + linkable `per=film`), plus a one-line "N uses per film" summary per word.

**Architecture:** A tiny new bake file `json/year-films.json` (films per release year) beside every `year-totals.json` (global + 34 language slices) is the per-film denominator. `toSeries` keeps its raw rows so the view can re-divide counts by films without refetching; a `per=film` URL param picks the mode.

**Tech Stack:** Python 3 + DuckDB (pipeline, pytest via `uv`), React 19 + TypeScript + Vite + vitest (app), rclone -> Cloudflare R2, GitHub Actions auto-deploy to Cloudflare Pages on merge.

Spec: `docs/superpowers/specs/2026-09-24-trends-per-film-design.md`.

## Global Constraints

- All UI copy in `app/src/messages/en.json` only, rendered via `useI18n()` `t`/`n`; never edit the other 32 locale files by hand (pre-commit hook regenerates them; CI checks key parity).
- Site copy uses " - " (spaced hyphen), never em-dashes.
- `n()` for displayed numbers; never `n()` 4-digit years.
- Data must be live on R2 **before** the app PR merges (merge auto-deploys).
- Year trimming stays `MIN_YEAR_WORDS` on word totals in both modes.
- Work in worktree `/Users/andrew/Projects/beveradb/moviewords-trends-per-film` (branch `feat/trends-per-film`).
- App commands run from `app/`: `npm test`, `npm run lint`, `npm run build`. Pipeline tests from `pipeline/`: `uv run pytest`.

---

### Task 1: Pipeline - bake `year-films.json` + upload rule

**Files:**
- Modify: `pipeline/scripts/rebuild_web_data.py` (add `write_year_films`, `stage_yearfilms`; call from `stage_trends`; register stage)
- Modify: `pipeline/scripts/upload_r2.sh:9-12,50-57` (comment + filter rules)
- Test: `pipeline/tests/test_stage_trends.py`

**Interfaces:**
- Produces: `webdata/out[/all[/lang/<code>]]/json/year-films.json` = `{"<year>": <int films>}`; CLI `--stage yearfilms`.

- [ ] **Step 1: Write the failing tests** - append to `pipeline/tests/test_stage_trends.py`:

```python
def test_write_year_films_counts_films_per_year(tmp_path, monkeypatch):
    import rebuild_web_data as rwd
    monkeypatch.setattr(rwd, "OUT", tmp_path)
    con = duckdb.connect()
    con.sql("""
        CREATE TABLE movies (imdb_id VARCHAR, year INT);
        INSERT INTO movies VALUES ('a', 2001), ('b', 2001), ('c', 1952), ('d', NULL);
    """)
    rwd.write_year_films(con)
    films = json.loads((tmp_path / "json" / "year-films.json").read_text())
    assert films == {"1952": 1, "2001": 2}


def test_yearfilms_is_a_registered_stage():
    import rebuild_web_data as rwd
    assert rwd.STAGES["yearfilms"] is rwd.stage_yearfilms
```

and in the existing `test_stage_trends_bakes_line_top_byyear`, after the `totals` assert, add:

```python
    films = json.loads((tmp_path / "json" / "year-films.json").read_text())
    assert films == {"1952": 1, "1999": 1, "2001": 1}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && uv run pytest tests/test_stage_trends.py -v`
Expected: FAIL - `AttributeError: ... has no attribute 'write_year_films'` / `KeyError: 'yearfilms'`.

- [ ] **Step 3: Implement** in `pipeline/scripts/rebuild_web_data.py`. Add above `stage_trends`:

```python
def write_year_films(con):
    """json/year-films.json: films released per year in this corpus/slice -
    the Trends page's per-film denominator (a word's yearly count / films)."""
    rows = con.sql(
        "SELECT year, count(*)::BIGINT FROM movies WHERE year IS NOT NULL "
        "GROUP BY year ORDER BY year").fetchall()
    (OUT / "json").mkdir(parents=True, exist_ok=True)
    (OUT / "json" / "year-films.json").write_text(
        json.dumps({str(y): n for y, n in rows}))


def stage_yearfilms(con):
    """Standalone so the 35 small files can be (re)baked + uploaded without
    regenerating ~485k per-word trend JSONs."""
    write_year_films(con)
```

In `stage_trends`, directly after the `year-totals.json` `write_text(...)` call add:

```python
    write_year_films(con)
```

Register it:

```python
STAGES = {"meta": stage_meta, "movies": stage_movies,
          "boards": stage_boards, "signatures": stage_signatures,
          "featured": stage_featured, "trends": stage_trends,
          "yearfilms": stage_yearfilms}
```

Add to the module docstring's stage list (after the `trends` entry):

```
  yearfilms   json/year-films.json only (films per year; also written by trends)
```

- [ ] **Step 4: Update `pipeline/scripts/upload_r2.sh`** - `year-films.json` gets the same 1h TTL as `year-totals.json`. In the first `rclone copy` (the `max-age=3600` one) add after the year-totals line:

```bash
  --filter '+ json/year-films.json' --filter '+ all/json/year-films.json' --filter '+ all/lang/*/json/year-films.json' \
```

and in the second (`max-age=300`) add after its year-totals exclude line:

```bash
  --filter '- json/year-films.json' --filter '- all/json/year-films.json' --filter '- all/lang/*/json/year-films.json' \
```

In the header comment (lines ~11-12), change `json/trend/** + year-totals.json` to `json/trend/** + year-totals.json + year-films.json` (both mentions).

- [ ] **Step 5: Run tests**

Run: `cd pipeline && uv run pytest tests/test_stage_trends.py tests/test_bake_all_languages.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/rebuild_web_data.py pipeline/scripts/upload_r2.sh pipeline/tests/test_stage_trends.py
git commit -m "feat(pipeline): bake json/year-films.json (films per year) for per-film trends"
```

---

### Task 2: Bake + publish `year-films.json` to R2 (ops)

Data first - the app must not depend on a file that isn't live.

**Files:** none committed. Uses the main checkout's (gitignored) `pipeline/webdata`.

**Interfaces:**
- Consumes: Task 1's `--stage yearfilms`.
- Produces: live `https://data.moviewords.org/all/json/year-films.json` and `.../all/lang/<code>/json/year-films.json` for all 34 codes in `all/json/languages.json`.

- [ ] **Step 1: Link the inputs into the worktree**

```bash
cd /Users/andrew/Projects/beveradb/moviewords-trends-per-film/pipeline
ln -s /Users/andrew/Projects/beveradb/moviewords/pipeline/webdata webdata
ls webdata/in/all/movies.parquet webdata/in/all/lang/es/movies.parquet
```
Expected: both paths listed.

- [ ] **Step 2: Bake global + every language**

```bash
uv run python scripts/rebuild_web_data.py --corpus all --stage yearfilms
for code in $(python3 -c "import json;print(' '.join(o['code'] for o in json.load(open('webdata/out/all/json/languages.json'))))"); do
  uv run python scripts/rebuild_web_data.py --corpus all --lang "$code" --stage yearfilms >/dev/null || echo "FAILED $code"
done
ls webdata/out/all/lang/*/json/year-films.json | wc -l
```
Expected: no `FAILED`, count `34`.

- [ ] **Step 3: Sanity-check the numbers**

```bash
python3 - <<'EOF'
import json
g = json.load(open('webdata/out/all/json/year-films.json'))
print(sum(g.values()), g['1969'], g['2019'])
es = json.load(open('webdata/out/all/lang/es/json/year-films.json'))
print(sum(es.values()))
EOF
```
Expected: global sum ≈ 51,624 (all films with a year); plausible per-year counts (hundreds in 1969, thousands in 2019); es sum in the low thousands.

- [ ] **Step 4: Upload only these 35 files** (R2 creds derived from `MOVIEWORDS_CF_TOKEN` per the `moviewords-deploy-ops` memory: access key = `GET /user/tokens/verify` `.result.id`, secret = sha256(token), account = `GET /accounts` `.result[0].id`; source `/Users/andrew/Projects/beveradb/.envrc` first)

```bash
cd webdata/out
export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
  RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  RCLONE_CONFIG_R2_ENDPOINT="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
rclone copy . r2:moviewords-data/ --checksum \
  --filter '+ all/json/year-films.json' --filter '+ all/lang/*/json/year-films.json' --filter '- *' \
  --header-upload "Cache-Control: public, max-age=3600"
```

- [ ] **Step 5: Verify live**

```bash
for p in all/json/year-films.json all/lang/es/json/year-films.json all/lang/ja/json/year-films.json; do
  curl -s -o /dev/null -w "%{http_code} $p\n" "https://data.moviewords.org/$p"; done
curl -s -H 'Origin: http://localhost:5173' -I https://data.moviewords.org/all/json/year-films.json | grep -i access-control-allow-origin
```
Expected: three `200`s; a CORS allow-origin header present.

---

### Task 3: Pure trends logic - per-film series, summary, href, number format

**Files:**
- Modify: `app/src/lib/trends.ts` (extend `WordSeries`, `toSeries`; add `perFilmSeries`, `perFilmSummary`, `trendsHref`, `isPerFilm`, `formatPerFilm`)
- Test: `app/src/lib/trends.test.ts`

**Interfaces:**
- Produces (exact):
  - `interface WordSeries { series: Series[]; plottedYears: number[]; trimmedYears: string | null; missing: string[]; rows: YearRow[]; totals: Map<number, number> }` (`rows` = the kept rows only)
  - `perFilmSeries(ws: WordSeries, films: Map<number, number>): Series[]`
  - `perFilmSummary(ws: WordSeries, films: Map<number, number>, word: string): { decade: number; latest: number; overall: number } | null`
  - `trendsHref(words: string[], perFilm: boolean): string` -> `/trends?w=<enc>` or `/trends?w=<enc>&per=film`
  - `isPerFilm(params: URLSearchParams): boolean`
  - `formatPerFilm(v: number, n: (v: number, o?: Intl.NumberFormatOptions) => string): string`

- [ ] **Step 1: Write failing tests** - add `perFilmSeries, perFilmSummary, trendsHref, isPerFilm, formatPerFilm` to the import list at the top of `app/src/lib/trends.test.ts`, then append:

```ts
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
  it('builds a linkable URL, adding per=film only when on', () => {
    expect(trendsHref(['fuck', "don't"], false)).toBe(`/trends?w=${encodeURIComponent("fuck,don't")}`)
    expect(trendsHref(['fuck'], true)).toBe('/trends?w=fuck&per=film')
  })
  it('reads the per param', () => {
    expect(isPerFilm(new URLSearchParams('w=a&per=film'))).toBe(true)
    expect(isPerFilm(new URLSearchParams('w=a'))).toBe(false)
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app && npx vitest run src/lib/trends.test.ts`
Expected: FAIL - imports not exported / `ws.rows` undefined.

- [ ] **Step 3: Implement** in `app/src/lib/trends.ts`.

Replace the `WordSeries` interface:

```ts
export interface WordSeries {
  series: Series[]
  plottedYears: number[]
  trimmedYears: string | null
  missing: string[]
  /** The kept (non-trimmed) raw rows + the denominator used, so a view can
   * re-divide (e.g. per film) without refetching. */
  rows: YearRow[]
  totals: Map<number, number>
}
```

In `toSeries`, change the final `return` to:

```ts
  return { series, plottedYears, trimmedYears, missing, rows: kept, totals }
```

Append to the file:

```ts
/** Re-divide a word series' yearly counts by films released that year
 * (average uses per film). Years without a film count are dropped. */
export function perFilmSeries(ws: WordSeries, films: Map<number, number>): Series[] {
  const counts = new Map(ws.rows.map((r) => [`${r.word}|${r.year}`, r.count]))
  return ws.series.map((s) => ({
    ...s,
    points: s.points.flatMap((p) => {
      const f = films.get(p.x)
      const c = counts.get(`${s.name}|${p.x}`)
      return f && c !== undefined ? [{ ...p, y: c / f }] : []
    }),
  }))
}

/** "N uses per film in the <decade>s (all years: M)": pooled averages over the
 * plotted years (a plotted year the word is absent from counts as 0 uses). */
export function perFilmSummary(
  ws: WordSeries,
  films: Map<number, number>,
  word: string,
): { decade: number; latest: number; overall: number } | null {
  const counts = new Map(ws.rows.filter((r) => r.word === word).map((r) => [r.year, r.count]))
  if (!counts.size || !ws.plottedYears.length) return null
  const decade = Math.floor(ws.plottedYears[ws.plottedYears.length - 1] / 10) * 10
  const avg = (years: number[]) => {
    let c = 0
    let f = 0
    for (const y of years) {
      c += counts.get(y) ?? 0
      f += films.get(y) ?? 0
    }
    return f ? c / f : 0
  }
  return {
    decade,
    latest: avg(ws.plottedYears.filter((y) => y >= decade)),
    overall: avg(ws.plottedYears),
  }
}

/** Trends URL for a word list; `per=film` only when the per-film view is on,
 * so default links stay unchanged. */
export const trendsHref = (words: string[], perFilm: boolean): string =>
  `/trends?w=${encodeURIComponent(words.join(','))}${perFilm ? '&per=film' : ''}`

export const isPerFilm = (params: URLSearchParams): boolean => params.get('per') === 'film'

/** Per-film averages are often < 1: 1 decimal from 1 up, 2 below, "<0.01"
 * for tiny non-zero values. `n` is the i18n number formatter. */
export function formatPerFilm(v: number, n: (v: number, o?: Intl.NumberFormatOptions) => string): string {
  if (v === 0) return n(0)
  if (v < 0.01) return `<${n(0.01, { minimumFractionDigits: 2 })}`
  const d = v >= 1 ? 1 : 2
  return n(v, { minimumFractionDigits: d, maximumFractionDigits: d })
}
```

- [ ] **Step 4: Run tests**

Run: `cd app && npx vitest run src/lib/trends.test.ts && npx tsc -b`
Expected: PASS, no type errors. (If `tsc` flags any other place constructing a `WordSeries` literal, add `rows: []`/`totals` there - `toSeries` is the only constructor today.)

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/trends.ts app/src/lib/trends.test.ts
git commit -m "feat(trends): per-film series, summary, href helpers"
```

---

### Task 4: Load `year-films.json` (language-aware, cached)

**Files:**
- Modify: `app/src/lib/series.ts` (generalise `bakedYearTotals` into `bakedYearMap`; export `bakedYearFilms`)
- Test: `app/src/lib/series.test.ts`

**Interfaces:**
- Produces: `export function bakedYearFilms(): Promise<Map<number, number>>`

- [ ] **Step 1: Write failing tests** - replace the top of `app/src/lib/series.test.ts` imports and append:

```ts
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
```

(keep the existing `mergeTrendFiles` describe block unchanged), then append:

```ts
describe('bakedYearFilms', () => {
  it('reads the global file when no language filter is active', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ '2000': 3, '2001': 4 })))
    vi.stubGlobal('fetch', fetchMock)
    const m = await bakedYearFilms()
    expect([...m]).toEqual([[2000, 3], [2001, 4]])
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/all\/json\/year-films\.json$/)
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app && npx vitest run src/lib/series.test.ts`
Expected: FAIL - `bakedYearFilms` is not exported.

- [ ] **Step 3: Implement** in `app/src/lib/series.ts`. Replace `let yearTotalsBakeCache ...` through the end of `bakedYearTotals` with:

```ts
// keyed by file + selected languages so a filter change never serves a stale map
const yearMapCache = new Map<string, Promise<Map<number, number>>>()

const toYearMap = (obj: Record<string, number>) =>
  new Map(Object.entries(obj).map(([y, t]) => [Number(y), t]))

/** A pre-baked per-year number map (a couple of KB), cached for the session.
 * 0 languages -> the global file; 1+ -> fetch + sum the selected languages'
 * files. year-totals.json = words per year (rate denominator); year-films.json
 * = films per year (per-film denominator). */
function bakedYearMap(file: 'year-totals.json' | 'year-films.json'): Promise<Map<number, number>> {
  const langs = activeLanguages()
  const key = `${file}|${langs.join(',')}`
  const hit = yearMapCache.get(key)
  if (hit) return hit
  const p = (async () => {
    if (!langs.length) return toYearMap(await fetchJSON<Record<string, number>>(`json/${file}`))
    const maps = await Promise.all(
      langs.map(async (code) => {
        const res = await fetch(langUrl(code, `json/${file}`))
        if (!res.ok) throw new Error(`${res.status} fetching ${file} [${code}]`)
        return toYearMap(await res.json())
      }),
    )
    return mergeYearTotals(maps)
  })()
  // a failed fetch must not be cached forever
  p.catch(() => yearMapCache.delete(key))
  yearMapCache.set(key, p)
  return p
}

const bakedYearTotals = () => bakedYearMap('year-totals.json')

/** Films released per year (language-aware) - the Trends per-film denominator. */
export const bakedYearFilms = () => bakedYearMap('year-films.json')
```

(`bakedYearTotals()` call sites are unchanged.)

- [ ] **Step 4: Run tests**

Run: `cd app && npx vitest run src/lib/series.test.ts && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/series.ts app/src/lib/series.test.ts
git commit -m "feat(trends): language-aware year-films loader"
```

---

### Task 5: Chart handles values below 1

**Files:**
- Create: `app/src/lib/chartFormat.ts`
- Test: `app/src/lib/chartFormat.test.ts`
- Modify: `app/src/components/LineChart.tsx:64,161,211`

**Interfaces:**
- Produces: `formatChartValue(v: number): string`

- [ ] **Step 1: Write the failing test** `app/src/lib/chartFormat.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatChartValue } from './chartFormat'

describe('formatChartValue', () => {
  it('keeps 1 decimal from 1 up', () => {
    expect(formatChartValue(845)).toBe('845')
    expect(formatChartValue(10.46)).toBe('10.5')
  })
  it('keeps 2 significant digits below 1 (per-film averages)', () => {
    expect(formatChartValue(0.054)).toBe('0.054')
    expect(formatChartValue(0.30000000000000004)).toBe('0.3')
  })
  it('shows zero as 0', () => {
    expect(formatChartValue(0)).toBe('0')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app && npx vitest run src/lib/chartFormat.test.ts`
Expected: FAIL - module not found.

- [ ] **Step 3: Implement** `app/src/lib/chartFormat.ts`:

```ts
/** Chart tick/tooltip value. Per-million rates are big (1 decimal is plenty);
 * per-film averages are often < 1, where 1 decimal would flatten them to 0. */
export function formatChartValue(v: number): string {
  if (v === 0) return '0'
  if (Math.abs(v) >= 1) return String(Math.round(v * 10) / 10)
  return String(Number(v.toPrecision(2)))
}
```

In `app/src/components/LineChart.tsx`:
- add `import { formatChartValue } from '../lib/chartFormat'`
- line ~64: `yMax: Math.max(...ys, 1)` -> `yMax: Math.max(...ys) > 0 ? Math.max(...ys) : 1`
- line ~161: `{tick >= 1000 ? `${tick / 1000}k` : Math.round(tick * 10) / 10}` -> `{tick >= 1000 ? `${tick / 1000}k` : formatChartValue(tick)}`
- line ~211: `{Math.round(p.y * 10) / 10}` -> `{formatChartValue(p.y)}`

- [ ] **Step 4: Run tests**

Run: `cd app && npm test && npx tsc -b`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/chartFormat.ts app/src/lib/chartFormat.test.ts app/src/components/LineChart.tsx
git commit -m "fix(chart): readable ticks/tooltips for values below 1"
```

---

### Task 6: Trends page - toggle, per-film chart, summary line, copy

**Files:**
- Modify: `app/src/views/Trends.tsx`
- Modify: `app/src/messages/en.json` (`trends` block) - locale files regenerate via the pre-commit hook

**Interfaces:**
- Consumes: `perFilmSeries`, `perFilmSummary`, `trendsHref`, `isPerFilm`, `formatPerFilm`, `WordSeries` (Task 3); `bakedYearFilms` (Task 4).

- [ ] **Step 1: Add copy** to the `"trends"` object in `app/src/messages/en.json` (after `"usesPerMillionWords"`):

```json
    "measureAriaLabel": "Measure",
    "perMillionToggle": "Per million words",
    "perFilmToggle": "Per film",
    "yAxisLabelPerFilm": "uses per film",
    "usesPerFilmCaption": "average uses per film released that year",
    "perFilmSummary": "“{word}”: {latest} uses per film in {decade}s films (all years: {overall})",
```

- [ ] **Step 2: Wire the view** in `app/src/views/Trends.tsx`:

Imports: add `perFilmSeries, perFilmSummary, trendsHref, isPerFilm, formatPerFilm, type WordSeries` to the `../lib/trends` import and `bakedYearFilms` to the `../lib/series` import (create the import lines if the names come from elsewhere today - check the file's existing imports).

In `TrendsView`, after `const words = useMemo(...)`:

```tsx
  const perFilm = isPerFilm(params)
  const [wordSeries, setWordSeries] = useState<WordSeries | null>(null)
  const [films, setFilms] = useState<Map<number, number> | null>(null)
  const [filmsError, setFilmsError] = useState<string | null>(null)

  useEffect(() => {
    bakedYearFilms().then(setFilms).catch((e) => setFilmsError(String(e)))
  }, [])
```

In the data effect, in the featured branch `.then(...)` add `setWordSeries(ws)` - i.e. change the callback to:

```tsx
        .then((ws) => {
          if (cancelled) return
          setWordSeries(ws)
          setSeries(ws.series)
          setPlottedYears(ws.plottedYears)
          setTrimmedYears(ws.trimmedYears)
          setMissing(ws.missing)
        })
```

and in the `loadTrends` branch add `setWordSeries(wordSeries)` as the first line after the `cancelled` check.

Replace the `notedSeries` memo with:

```tsx
  // per-film mode re-divides the same counts by films per year (no refetch)
  const shownSeries = useMemo(() => {
    if (!series) return series
    return perFilm && wordSeries && films ? perFilmSeries({ ...wordSeries, series }, films) : series
  }, [series, wordSeries, films, perFilm])

  // graft top-movie notes onto the chart series once (if) they arrive
  const notedSeries = useMemo(() => {
    if (!shownSeries || !topMovies) return shownSeries
    return shownSeries.map((s) => ({
      ...s,
      points: s.points.map((p) => {
        const top = topMovies.get(s.name)?.get(p.x)
        return top ? { ...p, note: top.title, noteHref: `#/movie/${top.imdb_id}` } : p
      }),
    }))
  }, [shownSeries, topMovies])
```

Replace the three word-list `navigate(...)` calls in this component:
- in `addWord`: `navigate(trendsHref([...new Set([...words, w])].slice(0, MAX_WORDS), perFilm))`
- chip remove: `onClick={() => navigate(trendsHref(words.filter((x) => x !== w), perFilm))}`
- "try a classic" buttons: `onClick={() => navigate(trendsHref([w], perFilm))}`

Add the per-film error just after `{error && <ErrorBox message={error} />}`:

```tsx
      {perFilm && filmsError && <ErrorBox message={filmsError} />}
```

Inside the chart card, directly before `{featured && <SeriesLegend .../>}`, add the toggle:

```tsx
          <div className="mb-3 flex gap-1" role="group" aria-label={t('trends.measureAriaLabel')}>
            {([false, true] as const).map((on) => (
              <button
                key={String(on)}
                type="button"
                aria-pressed={perFilm === on}
                onClick={() => navigate(trendsHref(words, on))}
                className={`border-2 border-ink px-2.5 py-1 font-script text-xs ${perFilm === on ? 'bg-ink text-paper' : 'bg-card hover:bg-paper-2'}`}
              >
                {on ? t('trends.perFilmToggle') : t('trends.perMillionToggle')}
              </button>
            ))}
          </div>
```

(Check the actual inverse-colour class names used elsewhere for a "selected" state - e.g. the nav's active tab in `App.tsx` - and use those instead of `bg-ink text-paper` if they differ.)

Replace the `LineChart` line and caption with:

```tsx
          <LineChart series={notedSeries} yLabel={perFilm ? t('trends.yAxisLabelPerFilm') : t('trends.yAxisLabel')} />
          <p className="mt-2 text-end text-xs text-ink-2">
            {perFilm ? t('trends.usesPerFilmCaption') : t('trends.usesPerMillionWords')}
          </p>
```

After the `trimmedYears` note (still inside the card), add the summary:

```tsx
          {!featured && wordSeries && films && (
            <div className="mt-3 space-y-0.5 border-t-2 border-ink pt-2 font-script text-sm">
              {words.map((w) => {
                const s = perFilmSummary(wordSeries, films, w)
                return s ? (
                  <p key={w}>
                    {t('trends.perFilmSummary', {
                      word: w,
                      latest: formatPerFilm(s.latest, n),
                      decade: s.decade,
                      overall: formatPerFilm(s.overall, n),
                    })}
                  </p>
                ) : null
              })}
            </div>
          )}
```

In per-film mode, if films haven't arrived yet the chart would briefly show per-million values - avoid that: change the chart card condition `{notedSeries && notedSeries.length > 0 && !loading && (` to `{notedSeries && notedSeries.length > 0 && !loading && (!perFilm || films) && (`.

- [ ] **Step 3: Type-check, lint, test**

Run: `cd app && npx tsc -b && npm run lint && npm test`
Expected: no new errors (oxlint has 3 pre-existing rules-of-hooks errors in `LineChart.tsx` on main - ignore those only), tests pass.

- [ ] **Step 4: Try it locally** (vite MUST be on port 5173 - R2 CORS allows only that origin locally)

```bash
cd app && npm run dev -- --port 5173 --strictPort
```

With Playwright at 1200px and 390px wide:
- `http://localhost:5173/#/trends?w=fuck` - summary line reads about "“fuck”: 12… uses per film in 2020s films (all years: …)"; chart unchanged.
- click "Per film" - URL gains `&per=film`, y axis "uses per film", values ~0-20; tooltip values sensible.
- `#/trends?w=swell&per=film` - small values render with 2 decimals, chart not flattened.
- add a word while in per-film mode - `per=film` preserved.
- `#/trends?per=film` (featured) - toggle works, no summary.
- with a language filter (e.g. Spanish) - chart + summary still render.

- [ ] **Step 5: Commit** (the pre-commit hook translates the new keys into the 32 locales and stages them; needs GCP ADC)

```bash
git add app/src/views/Trends.tsx app/src/messages/en.json
git commit -m "feat(trends): per-film toggle + average-uses-per-film summary"
git show --stat HEAD | grep messages | wc -l
```
Expected: 33 message files in the commit. If the hook couldn't translate (auth), run `cd app && npm run translate`, then `git add app/src/messages && git commit --amend --no-edit`. Then `npm run translate:validate` passes.

---

### Task 7: Ship

- [ ] **Step 1:** `cd app && npm test && npm run build` - pass.
- [ ] **Step 2:** Confirm Task 2's files are live (re-run Task 2 Step 5).
- [ ] **Step 3:** Push + open PR (no local CodeRabbit pass is possible - CLI is SSO-blocked - so omit `@coderabbitai ignore`), wait for the i18n check, squash-merge. Merge auto-deploys via `.github/workflows/deploy.yml`.
- [ ] **Step 4:** Watch the deploy workflow to success (`gh run watch`), then on https://moviewords.org hard-reload and repeat Task 6 Step 4's checks against prod, incl. `https://moviewords.org/#/trends?w=fuck&per=film`.
