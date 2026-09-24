// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import { Poster } from './ui'

describe('Poster', () => {
  it('offers AVIF with a JPEG fallback', async () => {
    let container!: HTMLElement
    await act(async () => {
      ;({ container } = render(<I18nProvider><Poster id="tt0068646" title="The Godfather" className="w-full" /></I18nProvider>))
    })
    const source = container.querySelector('picture > source')
    expect(source?.getAttribute('srcset')).toBe('https://data.moviewords.org/posters/tt0068646.avif')
    expect(source?.getAttribute('type')).toBe('image/avif')
    const img = container.querySelector('picture > img')
    expect(img?.getAttribute('src')).toBe('https://data.moviewords.org/posters/tt0068646.jpg')
    expect(img?.className).toContain('aspect-[2/3]')
    expect(img?.className).toContain('w-full')
  })

  it('falls back to the title placeholder when the image fails', async () => {
    let container!: HTMLElement
    await act(async () => {
      ;({ container } = render(<I18nProvider><Poster id="tt0000000" title="Lost Film" /></I18nProvider>))
    })
    await act(async () => { fireEvent.error(container.querySelector('img')!) })
    expect(container.querySelector('picture')).toBeNull()
    expect(screen.getByText('Lost Film')).toBeTruthy()
  })
})
