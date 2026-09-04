/**
 * The grading and bankroll rules. These decide whether a user's record is
 * right, so the edge cases (a player who didn't suit up, a game not yet
 * played, a pick saved without a resolved week) are pinned here.
 */
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PRICE, STARTING_BANKROLL, gradePick, impliedProbability,
  profitFor, summarise, type GradedPick, type SavedPick,
} from './picks'

const basePick = (over: Partial<SavedPick> = {}): SavedPick => ({
  id: 'p1', player: 'Malik Nabers', team: 'NYG', opponent: 'BAL',
  stat: 'receiving_yards', line: 68.5, side: 'over', stake: 100,
  price: DEFAULT_PRICE, book: 'DraftKings', season: 2025, week: 4,
  gameday: '2025-09-28', modelProb: 0.31, savedAt: Date.parse('2025-09-25'),
  ...over,
})

const games = [
  { season: 2025, week: 3, receiving_yards: 90, opponent_team: 'KC', gameday: '2025-09-21' },
  { season: 2025, week: 4, receiving_yards: 20, opponent_team: 'BAL', gameday: '2025-09-28' },
]

describe('payout maths', () => {
  it('pays plus money proportionally', () => {
    expect(profitFor(100, +150)).toBeCloseTo(150, 6)
    expect(profitFor(50, +3300)).toBeCloseTo(1650, 6)
  })
  it('pays minus money as the inverse', () => {
    expect(profitFor(100, -110)).toBeCloseTo(90.909, 3)
    expect(profitFor(100, -1100)).toBeCloseTo(9.0909, 3)
  })
  it('treats a nonsense price as no profit rather than NaN', () => {
    expect(profitFor(100, 0)).toBe(0)
    expect(profitFor(100, Number.NaN)).toBe(0)
  })
  it('converts prices to implied probability', () => {
    expect(impliedProbability(-110)!).toBeCloseTo(0.5238, 4)
    expect(impliedProbability(+150)!).toBeCloseTo(0.4, 4)
    expect(impliedProbability(0)).toBeNull()
  })
})

describe('grading', () => {
  it('settles a losing over', () => {
    const g = gradePick(basePick(), games)
    expect(g.status).toBe('miss')
    expect(g.actual).toBe(20)
    expect(g.profit).toBe(-100)
  })

  it('settles a winning under at the captured price', () => {
    const g = gradePick(basePick({ side: 'under' }), games)
    expect(g.status).toBe('hit')
    expect(g.profit).toBeCloseTo(90.909, 3)
  })

  it('treats a line landing exactly on the number as an over', () => {
    const g = gradePick(basePick({ line: 20, side: 'over' }), games)
    expect(g.status).toBe('hit')
  })

  it('stays pending when the game has not been played', () => {
    const g = gradePick(basePick({ week: 9, gameday: '2099-01-01' }), games)
    expect(g.status).toBe('pending')
    expect(g.profit).toBe(0)
  })

  it('voids when the game was played but the player has no stat line', () => {
    // Injured or inactive — a sportsbook voids rather than scoring a loss.
    const g = gradePick(basePick({ week: 9, gameday: '2025-11-02' }), games,
      new Date('2025-12-01'))
    expect(g.status).toBe('void')
    expect(g.profit).toBe(0)
  })

  it('resolves the opponent game when no week was captured', () => {
    const g = gradePick(basePick({ week: null }), games)
    expect(g.status).toBe('miss')
    expect(g.actual).toBe(20)
  })

  it('voids when the stat is missing from the row', () => {
    const g = gradePick(basePick({ stat: 'rushing_yards' }), games)
    expect(g.status).toBe('void')
  })
})

describe('bankroll', () => {
  const graded = (over: Partial<GradedPick>): GradedPick =>
    ({ ...basePick(), status: 'hit', actual: 100, profit: 90.909, ...over }) as GradedPick

  it('starts from the opening bankroll with no picks', () => {
    const s = summarise([])
    expect(s.balance).toBe(STARTING_BANKROLL)
    expect(s.winRate).toBeNull()
    expect(s.roi).toBeNull()
  })

  it('counts profit only on settled picks', () => {
    const s = summarise([
      graded({ id: 'a', status: 'hit', profit: 90.909 }),
      graded({ id: 'b', status: 'miss', profit: -100 }),
      graded({ id: 'c', status: 'pending', profit: 0 }),
      graded({ id: 'd', status: 'void', profit: 0 }),
    ])
    expect(s.hits).toBe(1)
    expect(s.misses).toBe(1)
    expect(s.pending).toBe(1)
    expect(s.voids).toBe(1)
    expect(s.settled).toBe(2)
    expect(s.balance).toBeCloseTo(STARTING_BANKROLL - 9.091, 2)
    expect(s.winRate).toBeCloseTo(0.5, 6)
  })

  it('holds pending stakes at risk, out of available funds', () => {
    const s = summarise([graded({ status: 'pending', stake: 250, profit: 0 })])
    expect(s.atRisk).toBe(250)
    expect(s.available).toBe(STARTING_BANKROLL - 250)
  })

  it('excludes voided stakes from ROI', () => {
    const s = summarise([
      graded({ id: 'a', status: 'hit', stake: 100, profit: 90.909 }),
      graded({ id: 'v', status: 'void', stake: 900, profit: 0 }),
    ])
    expect(s.staked).toBe(100)
    expect(s.roi).toBeCloseTo(0.909, 3)
  })

  it('shows the trap in ranking by win rate alone', () => {
    // 92% correct on heavy favourites barely profits; ROI exposes it.
    const heavy = Array.from({ length: 100 }, (_, i) =>
      graded({ id: `h${i}`, price: -1100, stake: 100,
        status: i < 92 ? 'hit' : 'miss', profit: i < 92 ? profitFor(100, -1100) : -100 }))
    const s = summarise(heavy)
    expect(s.winRate).toBeCloseTo(0.92, 6)
    expect(s.roi!).toBeLessThan(0.01)   // a 92% record worth well under 1% ROI
  })
})
