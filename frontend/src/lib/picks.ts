/**
 * Saved picks and the virtual bankroll.
 *
 * Picks live in this browser only — there is no account and no server. That is
 * a deliberate first step rather than a limitation to work around: the hard
 * half of "did my pick hit?" needs no backend at all, because the daily data
 * bundle already carries every player's weekly game log. A pick grades itself
 * by looking up the week it was made for.
 *
 * Everything here is pure and synchronous apart from the storage calls, so the
 * grading and payout rules are unit-tested directly.
 *
 * The currency is imaginary. Nothing is purchasable, nothing cashes out, and
 * the bankroll resets with the season.
 */

export const STARTING_BANKROLL = 10_000
export const DEFAULT_PRICE = -110 // the standard price on a player prop

const STORAGE_KEY = 'gridedge-picks-v1'

export type PickSide = 'over' | 'under'
export type PickStatus = 'pending' | 'hit' | 'miss' | 'void'

export interface SavedPick {
  id: string
  player: string
  team: string
  opponent: string
  stat: string
  line: number
  side: PickSide
  stake: number
  /** American odds captured when the pick was saved, not looked up later. */
  price: number
  book: string | null
  season: number
  /** Week the pick applies to; null when the schedule couldn't resolve one. */
  week: number | null
  /** ISO date of the game, used to tell "not played yet" from "didn't play". */
  gameday: string | null
  /** What the model said at save time, so drift is visible afterwards. */
  modelProb: number | null
  savedAt: number
}

export interface GradedPick extends SavedPick {
  status: PickStatus
  /** The player's actual result, once known. */
  actual: number | null
  /** Coins won (positive) or lost (negative). Zero while pending or void. */
  profit: number
}

/** Profit on a winning bet at American odds. */
export function profitFor(stake: number, americanPrice: number): number {
  if (!Number.isFinite(americanPrice) || americanPrice === 0) return 0
  return americanPrice > 0
    ? stake * (americanPrice / 100)
    : stake * (100 / Math.abs(americanPrice))
}

/** The probability a price implies, including the book's margin. */
export function impliedProbability(price: number): number | null {
  if (!Number.isFinite(price) || price === 0) return null
  return price < 0 ? -price / (-price + 100) : 100 / (price + 100)
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

function read(): SavedPick[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    // Corrupt or unavailable storage shouldn't take the page down.
    return []
  }
}

function write(picks: SavedPick[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(picks))
  } catch {
    // Private browsing, or the quota is full — the pick just isn't remembered.
  }
}

export function loadPicks(): SavedPick[] {
  return read().sort((a, b) => b.savedAt - a.savedAt)
}

export function savePick(pick: Omit<SavedPick, 'id' | 'savedAt'>): SavedPick {
  const full: SavedPick = {
    ...pick,
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    savedAt: Date.now(),
  }
  write([full, ...read()])
  return full
}

export function deletePick(id: string): void {
  write(read().filter((p) => p.id !== id))
}

export function clearPicks(): void {
  write([])
}

/** Everything, as a file the user can keep — storage can be cleared. */
export function exportPicks(): string {
  return JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), picks: read() }, null, 2)
}

/** Merge an exported file back in, skipping picks already present. */
export function importPicks(json: string): { added: number; skipped: number } {
  const parsed = JSON.parse(json)
  const incoming: SavedPick[] = Array.isArray(parsed) ? parsed : parsed?.picks
  if (!Array.isArray(incoming)) throw new Error('That file does not contain saved picks.')

  const existing = read()
  const seen = new Set(existing.map((p) => p.id))
  const added = incoming.filter((p) => p && p.id && !seen.has(p.id))
  write([...added, ...existing])
  return { added: added.length, skipped: incoming.length - added.length }
}

// ---------------------------------------------------------------------------
// Grading
// ---------------------------------------------------------------------------

export interface GameRowLike {
  season: number
  week: number
  [stat: string]: number | string | null
}

/**
 * Settle a pick against the player's game log.
 *
 * Three outcomes beyond hit/miss matter:
 *  - the game hasn't happened yet, which is pending;
 *  - the game happened but the player has no stat line (inactive, injured),
 *    which voids the pick the way a sportsbook would rather than scoring it
 *    as a loss;
 *  - the pick never resolved a week, in which case the first game against
 *    that opponent after it was saved is used.
 */
export function gradePick(pick: SavedPick, games: GameRowLike[], today = new Date()): GradedPick {
  const base = { ...pick, status: 'pending' as PickStatus, actual: null as number | null, profit: 0 }

  const row = pick.week !== null
    ? games.find((g) => Number(g.season) === pick.season && Number(g.week) === pick.week)
    : games.find((g) => Number(g.season) === pick.season
        && String(g.opponent_team ?? '') === pick.opponent
        && new Date(String(g.gameday ?? '')).getTime() >= pick.savedAt)

  if (!row) {
    // No stat line. Either the game is still ahead of us, or it was played
    // without this player — only the schedule date can tell those apart.
    if (pick.gameday) {
      const kickoff = new Date(`${pick.gameday}T23:59:59`)
      if (Number.isFinite(kickoff.getTime()) && kickoff < today) {
        return { ...base, status: 'void' }
      }
    }
    return base
  }

  const value = row[pick.stat]
  if (typeof value !== 'number' || Number.isNaN(value)) return { ...base, status: 'void' }

  const hit = pick.side === 'over' ? value >= pick.line : value < pick.line
  return {
    ...base,
    status: hit ? 'hit' : 'miss',
    actual: value,
    profit: hit ? profitFor(pick.stake, pick.price) : -pick.stake,
  }
}

export interface BankrollSummary {
  balance: number
  atRisk: number
  available: number
  settled: number
  hits: number
  misses: number
  voids: number
  pending: number
  winRate: number | null
  roi: number | null
  staked: number
}

/** Bankroll and record across a set of graded picks. */
export function summarise(picks: GradedPick[]): BankrollSummary {
  let profit = 0
  let atRisk = 0
  let staked = 0
  const count = { hit: 0, miss: 0, void: 0, pending: 0 }

  for (const pick of picks) {
    count[pick.status] += 1
    if (pick.status === 'pending') {
      atRisk += pick.stake
    } else if (pick.status !== 'void') {
      profit += pick.profit
      staked += pick.stake
    }
  }

  const settled = count.hit + count.miss
  const balance = STARTING_BANKROLL + profit
  return {
    balance,
    atRisk,
    available: balance - atRisk,
    settled,
    hits: count.hit,
    misses: count.miss,
    voids: count.void,
    pending: count.pending,
    winRate: settled > 0 ? count.hit / settled : null,
    // Return on amount staked — the honest measure. A high win rate on heavy
    // favourites can still lose coins, which raw win count would hide.
    roi: staked > 0 ? profit / staked : null,
    staked,
  }
}
