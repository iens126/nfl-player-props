/**
 * Per-sportsbook accent colours.
 *
 * Deliberately colour only — no logos or wordmarks. Sportsbook marks are
 * registered trademarks, and the books licence them to affiliates under brand
 * agreements; reproducing them on an unaffiliated analytics site invites a
 * trademark problem and, worse, implies a partnership that doesn't exist.
 * A colour swatch next to the book's plain name gives the same instant
 * recognition in a comparison table without borrowing anyone's identity.
 *
 * Each book gets a light- and dark-theme value chosen to stay legible on this
 * app's backgrounds rather than to match the brand exactly — DraftKings' green
 * and FanDuel's blue are both far too bright on white at their true values.
 */

export interface BookStyle {
  /** Accent colour for the current theme. */
  color: string
  /** Two-letter monogram for the compact swatch. */
  initials: string
}

interface Palette {
  light: string
  dark: string
  initials: string
}

const BOOKS: Record<string, Palette> = {
  draftkings: { light: '#2F8F2F', dark: '#61D361', initials: 'DK' },
  fanduel: { light: '#1266C9', dark: '#5AA9FF', initials: 'FD' },
  betmgm: { light: '#9A7B33', dark: '#D9BA72', initials: 'MG' },
  caesars: { light: '#0F766E', dark: '#4FD1C5', initials: 'CZ' },
  pointsbet: { light: '#B03A2E', dark: '#F08A7E', initials: 'PB' },
  betrivers: { light: '#6D28D9', dark: '#A78BFA', initials: 'BR' },
  espnbet: { light: '#B91C1C', dark: '#F87171', initials: 'EB' },
  fanatics: { light: '#334155', dark: '#94A3B8', initials: 'FA' },
  bovada: { light: '#B45309', dark: '#FBBF24', initials: 'BV' },
}

const FALLBACK: Palette = { light: '#475569', dark: '#94A3B8', initials: '••' }

/** Normalise "DraftKings", "draftkings", "DK Sportsbook" to a lookup key. */
function keyFor(book: string): string {
  return book.toLowerCase().replace(/[^a-z]/g, '')
}

export function bookStyle(book: string, isDark: boolean): BookStyle {
  const key = keyFor(book)
  const palette = BOOKS[key]
    // Tolerate suffixed names like "DraftKings Sportsbook".
    ?? Object.entries(BOOKS).find(([name]) => key.startsWith(name))?.[1]
    ?? FALLBACK

  return {
    color: isDark ? palette.dark : palette.light,
    initials: palette === FALLBACK
      ? book.slice(0, 2).toUpperCase()
      : palette.initials,
  }
}
