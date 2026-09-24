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
