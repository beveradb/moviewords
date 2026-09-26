// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { I18nProvider } from '../i18n'
import { Poster, Slug } from './ui'

describe('Poster', () => {
  it('offers AVIF with a JPEG fallback', async () => {
    let container!: HTMLElement
    await act(async () => {
      ;({ container } = render(<I18nProvider><Poster id="tt0068646" title="The Godfather" className="w-full" /></I18nProvider>))
    })
    expect(container.querySelector('picture')?.className).toBe('contents')
    const source = container.querySelector('picture > source')
    expect(source?.getAttribute('srcset')).toBe('https://data.moviewords.org/posters/tt0068646.avif')
    expect(source?.getAttribute('type')).toBe('image/avif')
    const img = container.querySelector('picture > img')
    expect(img?.getAttribute('src')).toBe('https://data.moviewords.org/posters/tt0068646.jpg')
    expect(img?.className).toContain('aspect-[2/3]')
    expect(img?.className).toContain('w-full')
  })

  it('retries as plain JPEG when the AVIF fails, then placeholders if that fails too', async () => {
    let container!: HTMLElement
    await act(async () => {
      ;({ container } = render(<I18nProvider><Poster id="tt0000001" title="Half Lost" /></I18nProvider>))
    })
    const avifImg = container.querySelector('img')!
    Object.defineProperty(avifImg, 'currentSrc', { value: 'https://data.moviewords.org/posters/tt0000001.avif' })
    await act(async () => { fireEvent.error(avifImg) })
    expect(container.querySelector('picture')).toBeNull()
    const jpgImg = container.querySelector('img')!
    expect(jpgImg.getAttribute('src')).toBe('https://data.moviewords.org/posters/tt0000001.jpg')
    Object.defineProperty(jpgImg, 'currentSrc', { value: 'https://data.moviewords.org/posters/tt0000001.jpg' })
    await act(async () => { fireEvent.error(jpgImg) })
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('Half Lost')).toBeTruthy()
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

describe('Slug', () => {
  it('shows just the text when no prefix is given', () => {
    const { container } = render(<Slug text="GOODFELLAS - 1990" />)
    expect(container.querySelector('.slug > span')?.textContent).toBe('GOODFELLAS - 1990')
  })

  it('puts a given prefix before the text', () => {
    const { container } = render(<Slug prefix="2." text="GOODFELLAS" />)
    expect(container.querySelector('.slug > span')?.textContent).toBe('2. GOODFELLAS')
  })
})
