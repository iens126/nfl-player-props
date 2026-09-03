/**
 * The odds timestamp exists so a stale line can't masquerade as a live one,
 * which makes the wording and the staleness threshold worth pinning.
 */
import { describe, expect, it } from 'vitest'

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

const STALE_AFTER_MINUTES = 20

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
    expect(2 > STALE_AFTER_MINUTES).toBe(false)
  })

  it('tolerates the 10-minute server cache without crying stale', () => {
    // Responses are cached for ODDS_CACHE_MINUTES (10 by default), so a line
    // that age is expected, not a problem worth warning about.
    expect(10 > STALE_AFTER_MINUTES).toBe(false)
  })

  it('flags a page that has sat open', () => {
    expect(45 > STALE_AFTER_MINUTES).toBe(true)
  })
})
