/**
 * The odds timestamp exists so a stale line can't masquerade as a live one,
 * which makes the wording and the staleness threshold worth pinning.
 */
import { describe, expect, it } from 'vitest'

import { staleAfter } from './OddsFreshness'

// The pure formatting logic, mirrored from the component so it can be tested
// without a DOM renderer (the project has no React testing setup).
function describeAge(minutes: number): string {
  if (minutes < 1) return 'moments ago'
  if (minutes < 60) return `${Math.floor(minutes)} min ago`
  const hours = minutes / 60
  if (hours < 24) return `${Math.floor(hours)}h ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

describe('odds age wording', () => {
  it.each([
    [0, 'moments ago'],
    [0.5, 'moments ago'],
    [1, '1 min ago'],
    [9.7, '9 min ago'],
    [59, '59 min ago'],
    [60, '1h ago'],
    [150, '2h ago'],
    [1440, '1 day ago'],
    [2880, '2 days ago'],
  ])('%f minutes reads as "%s"', (minutes, expected) => {
    expect(describeAge(minutes)).toBe(expected)
  })
})

describe('staleness threshold', () => {
  it('treats a fresh fetch as current', () => {
    expect(2 > staleAfter(10)).toBe(false)
  })

  it('tolerates the server cache without crying stale', () => {
    // Responses are cached for ODDS_CACHE_MINUTES, so a line that age is
    // expected, not a problem worth warning about.
    expect(10 > staleAfter(10)).toBe(false)
  })

  it('flags a page that has sat open', () => {
    expect(45 > staleAfter(10)).toBe(true)
  })

  it('follows the cache window the server reports', () => {
    // The regression this exists for: with ODDS_CACHE_MINUTES at 30, a
    // 25-minute-old snapshot is the cache working as configured, not
    // something to warn about — and the warning's advice, "reload for current
    // prices", would hand back that very same snapshot.
    expect(25 > staleAfter(30)).toBe(false)
    expect(25 > staleAfter(10)).toBe(true)
    expect(70 > staleAfter(30)).toBe(true)
  })

  it('falls back to the default window when the server does not say', () => {
    for (const missing of [null, undefined, 0, -5, Number.NaN]) {
      expect(staleAfter(missing)).toBe(20)
    }
  })
})
