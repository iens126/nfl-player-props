/**
 * The special functions are the foundation everything else sits on, so they
 * are checked against values produced by Python's `math` module — the same
 * library the original engine used.
 */
import { describe, expect, it } from 'vitest'
import { erfc, lgamma, normalSf, quantileFromSorted } from './numerics'
import fixture from './numerics.fixture.json'

describe('erfc matches Python math.erfc', () => {
  it.each(fixture.erfc)('erfc(%f)', (x, expected) => {
    expect(erfc(x)).toBeCloseTo(expected, 9)
  })
})

describe('lgamma matches Python math.lgamma', () => {
  it.each(fixture.lgamma)('lgamma(%f)', (x, expected) => {
    // Relative tolerance: lgamma(1000) is ~5900, so absolute closeness is the
    // wrong test at the top of the range.
    expect(Math.abs(lgamma(x) - expected) / Math.max(Math.abs(expected), 1)).toBeLessThan(1e-10)
  })
})

describe('normalSf matches Python', () => {
  it.each(fixture.normal_sf)('normalSf(%f)', (x, expected) => {
    expect(normalSf(x)).toBeCloseTo(expected, 9)
  })
})

describe('quantileFromSorted matches numpy linear interpolation', () => {
  const sorted = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  it('hits exact values at the ends', () => {
    expect(quantileFromSorted(sorted, 0)).toBe(0)
    expect(quantileFromSorted(sorted, 1)).toBe(10)
  })
  it('interpolates between points', () => {
    expect(quantileFromSorted(sorted, 0.5)).toBeCloseTo(5, 10)
    expect(quantileFromSorted(sorted, 0.25)).toBeCloseTo(2.5, 10)
  })
  it('handles degenerate inputs', () => {
    expect(quantileFromSorted([], 0.5)).toBe(0)
    expect(quantileFromSorted([7], 0.9)).toBe(7)
  })
})
