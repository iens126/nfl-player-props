import type { Team } from '../api/types'

/**
 * Picking the two colours for the performance chart.
 *
 * The intent is that a bar is self-explanatory: the player's production is
 * drawn in their own team's colour, and what the opposing defense allows is
 * drawn in the defense's colour. Two things get in the way of just using the
 * primary colours as-is:
 *
 *  1. Some matchups pair near-identical primaries (a Cardinals/Falcons or
 *     Bears/Broncos chart would be two indistinguishable reds or oranges), so
 *     when the two are too close we fall back to the defense's secondary.
 *  2. Several teams' primaries are near-black or near-white, which disappear
 *     against one theme or the other, so colours are nudged into a legible
 *     lightness band for the active theme.
 */

interface Rgb {
  r: number
  g: number
  b: number
}

function hexToRgb(hex: string): Rgb | null {
  const clean = hex.trim().replace('#', '')
  const full = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  }
}

function rgbToHex({ r, g, b }: Rgb): string {
  const to = (v: number) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')
  return `#${to(r)}${to(g)}${to(b)}`
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
function luminance({ r, g, b }: Rgb): number {
  const channel = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** Perceptual-ish distance, weighted toward how different two colours *look*. */
function distance(a: Rgb, b: Rgb): number {
  const rMean = (a.r + b.r) / 2
  const dr = a.r - b.r
  const dg = a.g - b.g
  const db = a.b - b.b
  return Math.sqrt((2 + rMean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rMean) / 256) * db * db)
}

function mix(color: Rgb, target: Rgb, amount: number): Rgb {
  return {
    r: color.r + (target.r - color.r) * amount,
    g: color.g + (target.g - color.g) * amount,
    b: color.b + (target.b - color.b) * amount,
  }
}

const WHITE: Rgb = { r: 255, g: 255, b: 255 }
const BLACK: Rgb = { r: 0, g: 0, b: 0 }

/**
 * Keep a colour inside a lightness band that stays visible on the current
 * theme's background - near-black team colours get lifted on dark, near-white
 * ones get deepened on light.
 */
function makeLegible(rgb: Rgb, isDark: boolean): Rgb {
  const lum = luminance(rgb)
  if (isDark) {
    if (lum < 0.06) return mix(rgb, WHITE, 0.42)
    if (lum < 0.14) return mix(rgb, WHITE, 0.22)
    return rgb
  }
  if (lum > 0.75) return mix(rgb, BLACK, 0.38)
  if (lum > 0.55) return mix(rgb, BLACK, 0.18)
  return rgb
}

// Below this the two colours read as "the same colour" in a bar chart.
const MIN_DISTANCE = 120

export interface MatchupColors {
  player: string
  defense: string
  /** True when we had to move off the defense's primary to stay distinguishable. */
  adjusted: boolean
}

const FALLBACK_PLAYER = '#4f46e5'
const FALLBACK_DEFENSE = '#0e7490'

/**
 * Resolve the player-bar and defense-bar colours for a matchup.
 *
 * `playerTeam`/`defenseTeam` are abbreviations; both are looked up in the
 * teams list so this degrades gracefully when either is missing.
 */
export function matchupColors(
  playerTeam: string | null | undefined,
  defenseTeam: string | null | undefined,
  teams: Team[] | null,
  isDark: boolean,
): MatchupColors {
  const find = (abbr: string | null | undefined) =>
    abbr ? (teams ?? []).find((t) => t.abbr === abbr) ?? null : null

  const playerRgb = hexToRgb(find(playerTeam)?.color ?? '') ?? hexToRgb(FALLBACK_PLAYER)!
  const defTeam = find(defenseTeam)
  let defenseRgb = hexToRgb(defTeam?.color ?? '') ?? hexToRgb(FALLBACK_DEFENSE)!
  let adjusted = false

  if (distance(playerRgb, defenseRgb) < MIN_DISTANCE) {
    const secondary = hexToRgb(defTeam?.color2 ?? '')
    // Only take the secondary if it actually separates the two.
    if (secondary && distance(playerRgb, secondary) >= MIN_DISTANCE) {
      defenseRgb = secondary
      adjusted = true
    } else {
      defenseRgb = hexToRgb(FALLBACK_DEFENSE)!
      adjusted = true
    }
  }

  return {
    player: rgbToHex(makeLegible(playerRgb, isDark)),
    defense: rgbToHex(makeLegible(defenseRgb, isDark)),
    adjusted,
  }
}
