import type { LeaderboardRow } from './account'

/**
 * How the standings are ordered.
 *
 * Two boards, two different games. **Hits** rewards being right often; a
 * grinder taking heavy favourites can lead it while quietly losing coins.
 * **Return** rewards being right when it paid, so one brave longshot can take
 * the top from a standing start. Ranking only one of them would make the other
 * way of playing pointless, which is why both are here.
 *
 * Two rules are worth stating because neither is obvious from the numbers:
 *
 *  - Hits ties break on profit, not on who registered first. Two players on
 *    nine hits are not equal if one of them made money doing it.
 *  - Players below the staking floor sort beneath everyone above it in *both*
 *    directions. They are not ranked badly, they are not ranked yet, and
 *    flipping the column shouldn't promote them to the top.
 */

export type SortKey = 'hits' | 'return'
export type SortDirection = 'desc' | 'asc'

export function rankBoard(
  rows: LeaderboardRow[], sort: SortKey, dir: SortDirection,
): LeaderboardRow[] {
  const flip = dir === 'desc' ? 1 : -1
  return [...rows].sort((a, b) => {
    if (sort === 'hits') {
      if (a.hits !== b.hits) return (b.hits - a.hits) * flip
      if (a.profit !== b.profit) return (b.profit - a.profit) * flip
      return a.username.localeCompare(b.username)
    }
    if (a.roi_qualified !== b.roi_qualified) return a.roi_qualified ? -1 : 1
    if (a.roi === null || b.roi === null) return a.username.localeCompare(b.username)
    if (a.roi !== b.roi) return (b.roi - a.roi) * flip
    return a.username.localeCompare(b.username)
  })
}

/** Coins still to be staked before a player's return is ranked. */
export function stakeShortfall(row: LeaderboardRow): number {
  return Math.max(0, Math.ceil(row.roi_threshold - row.staked))
}
