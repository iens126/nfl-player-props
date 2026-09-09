/**
 * The ranking rules. These decide who is seen to be winning, so the cases that
 * aren't obvious from the column values — ties, and players who haven't staked
 * enough for a return to mean anything — are pinned here.
 */
import { describe, expect, it } from 'vitest'
import { rankBoard, stakeShortfall } from './leaderboard'
import type { LeaderboardRow } from './account'

const row = (over: Partial<LeaderboardRow>): LeaderboardRow => ({
  user_id: over.username ?? 'u', username: 'player', hits: 0, misses: 0, voids: 0,
  pending: 0, profit: 0, staked: 0, balance: 100, roi: null,
  roi_qualified: false, roi_threshold: 25, ...over,
})

const names = (rows: LeaderboardRow[]) => rows.map((r) => r.username)

describe('ranking by hits', () => {
  it('puts the most correct picks on top', () => {
    const board = [row({ username: 'ana', hits: 3 }), row({ username: 'bo', hits: 9 })]
    expect(names(rankBoard(board, 'hits', 'desc'))).toEqual(['bo', 'ana'])
  })

  it('breaks ties on profit, so being right cheaply counts for less', () => {
    const board = [
      row({ username: 'ana', hits: 9, profit: 4 }),
      row({ username: 'bo', hits: 9, profit: 40 }),
    ]
    expect(names(rankBoard(board, 'hits', 'desc'))).toEqual(['bo', 'ana'])
  })

  it('is stable on a full tie rather than depending on fetch order', () => {
    const board = [row({ username: 'zed', hits: 2 }), row({ username: 'ana', hits: 2 })]
    expect(names(rankBoard(board, 'hits', 'desc'))).toEqual(['ana', 'zed'])
  })
})

describe('ranking by return', () => {
  it('ranks on return, not on coins won', () => {
    // Doubling 30 coins beats grinding 50 out of 500: the point of the column.
    const bold = row({ username: 'bold', roi: 1.0, roi_qualified: true, profit: 30, staked: 30 })
    const grinder = row({ username: 'grinder', roi: 0.1, roi_qualified: true, profit: 50, staked: 500 })
    expect(names(rankBoard([grinder, bold], 'return', 'desc'))).toEqual(['bold', 'grinder'])
  })

  it('keeps players below the staking floor beneath everyone above it', () => {
    // A 1-coin winner at +2000 has a spectacular return and has risked nothing.
    const lucky = row({ username: 'lucky', roi: null, roi_qualified: false, staked: 1 })
    const real = row({ username: 'real', roi: -0.2, roi_qualified: true, staked: 200 })
    expect(names(rankBoard([lucky, real], 'return', 'desc'))).toEqual(['real', 'lucky'])
  })

  it('keeps them there when the column is reversed', () => {
    // Ascending should show the worst qualified return first, not promote
    // someone who hasn't qualified at all.
    const lucky = row({ username: 'lucky', roi: null, roi_qualified: false, staked: 1 })
    const real = row({ username: 'real', roi: -0.2, roi_qualified: true, staked: 200 })
    expect(names(rankBoard([lucky, real], 'return', 'asc'))).toEqual(['real', 'lucky'])
  })

  it('lets one big brave pick reach the top, which is the whole idea', () => {
    const bomb = row({ username: 'bomb', roi: 20, roi_qualified: true, staked: 100, profit: 2000 })
    const steady = row({ username: 'steady', roi: 0.15, roi_qualified: true, staked: 900 })
    expect(names(rankBoard([steady, bomb], 'return', 'desc'))).toEqual(['bomb', 'steady'])
  })

  it('does not mutate the array it was given', () => {
    const board = [row({ username: 'ana', hits: 1 }), row({ username: 'bo', hits: 5 })]
    rankBoard(board, 'hits', 'desc')
    expect(names(board)).toEqual(['ana', 'bo'])
  })
})

describe('the staking floor', () => {
  it('reports what is left to stake, rounded up to a whole coin', () => {
    expect(stakeShortfall(row({ staked: 12.4, roi_threshold: 25 }))).toBe(13)
  })
  it('never reports a shortfall once the floor is cleared', () => {
    expect(stakeShortfall(row({ staked: 90, roi_threshold: 25 }))).toBe(0)
  })
})
