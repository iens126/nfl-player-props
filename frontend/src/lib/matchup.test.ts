import { describe, expect, it } from 'vitest'
import { autoFillOpponent, nextOpponentFor, type OpponentPin } from './matchup'
import type { ScheduleGame } from '../api/types'

const game = (gameday: string, home: string, away: string): ScheduleGame => ({
  gameday, home_team: home, away_team: away, week: null,
})

describe('nextOpponentFor', () => {
  const schedule = [
    game('2026-09-13', 'SEA', 'NE'),
    game('2026-09-13', 'DAL', 'NYG'),
    game('2026-09-20', 'NE', 'BUF'),
    game('2026-09-27', 'SEA', 'DAL'),
  ]

  it('finds the opponent when the team is at home', () => {
    expect(nextOpponentFor(schedule, 'SEA')).toBe('NE')
  })

  it('finds the opponent when the team is away', () => {
    expect(nextOpponentFor(schedule, 'NYG')).toBe('DAL')
  })

  it('takes the soonest fixture, not the first listed', () => {
    // NE plays SEA on the 13th and BUF on the 20th.
    expect(nextOpponentFor(schedule, 'NE')).toBe('SEA')
  })

  it('is not fooled by an unsorted schedule', () => {
    // The array order says BUF; the dates say SEA. The dates win, because a
    // wrong answer here shows up as a plausible-looking wrong defense.
    const shuffled = [...schedule].reverse()
    expect(nextOpponentFor(shuffled, 'NE')).toBe('SEA')
  })

  it('returns null for a team with no upcoming game', () => {
    // A bye week, or a horizon that runs past the end of the season.
    expect(nextOpponentFor(schedule, 'KC')).toBeNull()
  })

  it('ignores a row listing a team against itself', () => {
    expect(nextOpponentFor([game('2026-09-13', 'SEA', 'SEA')], 'SEA')).toBeNull()
  })

  it('handles an empty or absent schedule', () => {
    expect(nextOpponentFor([], 'SEA')).toBeNull()
    expect(nextOpponentFor(null, 'SEA')).toBeNull()
    expect(nextOpponentFor(undefined, 'SEA')).toBeNull()
  })

  it('handles an absent team', () => {
    expect(nextOpponentFor(schedule, null)).toBeNull()
    expect(nextOpponentFor(schedule, '')).toBeNull()
  })
})

describe('autoFillOpponent', () => {
  const schedule = [
    game('2026-09-09', 'SEA', 'NE'),
    game('2026-09-13', 'NYG', 'DAL'),
    game('2026-09-13', 'MIN', 'GB'),
  ]
  const darnold = { player: 'Sam Darnold', team: 'SEA' }
  const lamb = { player: 'CeeDee Lamb', team: 'DAL' }

  it('fills in the fixture when nothing is pinned', () => {
    const r = autoFillOpponent({ pin: null, ...darnold, schedule, opponent: null })
    expect(r).toEqual({ opponent: 'NE', pin: null })
  })

  it('replaces the previous player’s defense when the player changes', () => {
    // The bug this whole rule exists for: DAL’s receiver must not be left
    // sitting against NE because a Seahawk was selected a moment ago.
    const r = autoFillOpponent({ pin: null, ...lamb, schedule, opponent: 'NE' })
    expect(r.opponent).toBe('NYG')
  })

  it('leaves a hand-picked defense alone for that player', () => {
    const r = autoFillOpponent({
      pin: 'Sam Darnold', ...darnold, schedule, opponent: 'GB',
    })
    expect(r).toEqual({ opponent: 'GB', pin: 'Sam Darnold' })
  })

  it('drops the pin once a different player is selected', () => {
    // The choice was about Darnold. It says nothing about Lamb — and the pin
    // has to clear, not just be ignored: the opponent now on screen came from
    // the fixture list, so nobody chose it.
    const r = autoFillOpponent({
      pin: 'Sam Darnold', ...lamb, schedule, opponent: 'GB',
    })
    expect(r).toEqual({ opponent: 'NYG', pin: null })
  })

  it('re-fills when returning to a player whose pin was already spent', () => {
    // The regression this cost a deploy to find. Pin Minnesota to Lamb, look
    // at a Seahawk, come back: Lamb must be against the Giants again, not left
    // on the defense that was filled in for somebody else.
    let pin: OpponentPin = 'CeeDee Lamb'
    let opponent: string | null = 'MIN'

    let r = autoFillOpponent({ pin, ...lamb, schedule, opponent })
    expect(r.opponent).toBe('MIN')
    ;({ pin, opponent } = r)

    r = autoFillOpponent({ pin, ...darnold, schedule, opponent })
    expect(r.opponent).toBe('NE')
    ;({ pin, opponent } = r)

    r = autoFillOpponent({ pin, ...lamb, schedule, opponent })
    expect(r.opponent).toBe('NYG')
  })

  it('carries a swapped-in defense to the next player chosen', () => {
    const r = autoFillOpponent({ pin: 'next', ...lamb, schedule, opponent: 'SEA' })
    expect(r).toEqual({ opponent: 'SEA', pin: 'CeeDee Lamb' })
  })

  it('then treats that as that player’s own choice', () => {
    const after = autoFillOpponent({ pin: 'next', ...lamb, schedule, opponent: 'SEA' })
    const again = autoFillOpponent({ pin: after.pin, ...lamb, schedule, opponent: 'SEA' })
    expect(again.opponent).toBe('SEA')
  })

  it('keeps the current defense for a player on a bye', () => {
    // Clearing it would empty the page out of season, when no team has a
    // fixture inside the horizon and every matchup is chosen by hand.
    const r = autoFillOpponent({
      pin: null, player: 'Patrick Mahomes', team: 'KC', schedule, opponent: 'NE',
    })
    expect(r.opponent).toBe('NE')
  })

  it('leaves the opponent null for a bye with nothing selected yet', () => {
    const r = autoFillOpponent({
      pin: null, player: 'Patrick Mahomes', team: 'KC', schedule, opponent: null,
    })
    expect(r.opponent).toBeNull()
  })

  it('survives the schedule not having loaded yet', () => {
    const r = autoFillOpponent({ pin: null, ...darnold, schedule: null, opponent: 'NE' })
    expect(r.opponent).toBe('NE')
  })

  it('follows a realistic sequence of selections', () => {
    // Link names both -> pinned to that player.
    let pin: OpponentPin = 'Sam Darnold'
    let opponent: string | null = 'GB'

    let r = autoFillOpponent({ pin, ...darnold, schedule, opponent })
    expect(r.opponent).toBe('GB')  // the link's choice holds
    ;({ pin, opponent } = r)

    // Switch to a Cowboy -> his own fixture.
    r = autoFillOpponent({ pin, ...lamb, schedule, opponent })
    expect(r.opponent).toBe('NYG')
    ;({ pin, opponent } = r)

    // Hand-pick a different defense for him.
    pin = 'CeeDee Lamb'
    opponent = 'MIN'
    r = autoFillOpponent({ pin, ...lamb, schedule, opponent })
    expect(r.opponent).toBe('MIN')  // held
    ;({ pin, opponent } = r)

    // Back to the Seahawk -> his fixture, not the Cowboy's choice.
    r = autoFillOpponent({ pin, ...darnold, schedule, opponent })
    expect(r.opponent).toBe('NE')
    ;({ pin, opponent } = r)

    // And back to the Cowboy -> his own fixture again, not the Seahawk's.
    r = autoFillOpponent({ pin, ...lamb, schedule, opponent })
    expect(r.opponent).toBe('NYG')
  })
})
