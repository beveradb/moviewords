// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import { WordExplorer } from './WordExplorer'

const data = { w: [['oh', 11, 40000], ['shoot', 6, 9000], ['sundance', 4, 1], ['shiiiit', 1, 12]] }

async function mount(initialQuery = '', body: unknown = data, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })))
  // the section is "seen" as soon as it's observed, so no-?q= mounts load too
  window.IntersectionObserver = class {
    cb: IntersectionObserverCallback
    constructor(cb: IntersectionObserverCallback) { this.cb = cb }
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

// this project doesn't set vitest's `test.globals: true`, so
// @testing-library/react's auto-cleanup (which looks for a global
// `afterEach`) never registers - clean up renders between tests ourselves.
afterEach(cleanup)
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
