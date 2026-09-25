// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import { MovieView } from './Movie'

const movie = {
  imdb_id: 'tt0022134', title: 'Arizona', year: 1931, original_language: 'en',
  stats: { total_words: 5440, unique_words: 900, words_per_minute: 77 },
  top: [['arizona', 12, 3, 'n', 'n']], top_all: [['you', 200, 7, 'n', 'n']], distinctive: [['arizona', 9, 3, 'n', 'n']],
}

async function mount(payload: object) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) =>
    String(url).includes('/json/movie/') ? new Response(JSON.stringify(payload))
      : String(url).includes('movies-index') ? new Response('[]')
        : new Response('', { status: 404 })))
  window.IntersectionObserver = class {
    observe() {}
    disconnect() {}
  } as unknown as typeof IntersectionObserver
  await act(async () => {
    render(<I18nProvider><MovieView id={`tt${Math.random()}`} /></I18nProvider>)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

afterEach(cleanup)
afterEach(() => vi.unstubAllGlobals())

describe('MovieView quality note', () => {
  it('explains why a low-quality film is left out of the aggregates', async () => {
    await mount({ ...movie, quality: { tier: 'low', flags: ['asr'] } })
    const note = screen.getByRole('note')
    expect(note.textContent).toMatch(/Subtitle quality: low/)
    expect(note.textContent).toMatch(/auto-generated captions/)
    expect(note.textContent).toMatch(/left out of every total/)
  })

  it('shows nothing for an ordinary film', async () => {
    await mount(movie)
    expect(screen.queryByRole('note')).toBeNull()
    expect(screen.getAllByText(/Arizona/).length).toBeGreaterThan(0)
  })
})
