/**
 * The projection's history, end to end in the browser engine.
 *
 * Every game counts, weighted by age: weights halve every HALF_LIFE_GAMES
 * games back and each offseason in between adds OFFSEASON_GAP_GAMES. A player
 * who hasn't played yet this season is projected from their history; the
 * moment they play once, that game joins the list at full weight. Nothing
 * resets at the season boundary, and nothing falls off a window's edge.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import type { Aggregates, GameRow, ModelsFile } from './bundle'
import { HALF_LIFE_GAMES, OFFSEASON_GAP_GAMES, decayWeights, recencyWeights, weightedMoments } from './models'
import { project } from './projection'

const DATA = join(__dirname, '../../public/data')
const read = (p: string) => JSON.parse(readFileSync(join(DATA, p), 'utf8'))

const aggregates: Aggregates = read('aggregates.json')
const models: ModelsFile = read('models.json')

function game(season: number, week: number, yards: number): GameRow {
  return { season, week, team: 'KC', opponent_team: 'DEN', position: 'WR', receiving_yards: yards }
}

const twoSeasonsBack = Array.from({ length: 17 }, (_, i) => game(2024, i + 1, 90))
const lastSeason = Array.from({ length: 18 }, (_, i) => game(2025, i + 1, i + 1))
const history = [...twoSeasonsBack, ...lastSeason]

function run(games: GameRow[]) {
  return project({
    player: 'Test Receiver', opponent: 'BAL', stat: 'receiving_yards', line: 10.5,
    model: 'ensemble', games, aggregates, models,
  })
}

function formAverage(games: GameRow[]) {
  const values = games.map((g) => g.receiving_yards as number)
  return weightedMoments(values, decayWeights(games.map((g) => g.season))).mean
}

describe('decay weights', () => {
  it('reduce to plain recency weighting within one season', () => {
    const one = decayWeights([2025, 2025, 2025, 2025])
    recencyWeights(4, HALF_LIFE_GAMES).forEach((w, i) => expect(one[i]).toBeCloseTo(w, 12))
  })

  it('count each offseason as OFFSEASON_GAP_GAMES more games back', () => {
    const w = decayWeights([2025, 2026])
    expect(w[0] / w[1]).toBeCloseTo(Math.pow(0.5, (1 + OFFSEASON_GAP_GAMES) / HALF_LIFE_GAMES), 12)
  })
})

describe('projection history across a season boundary', () => {
  it('uses every game, not a fixed window', () => {
    const result = run(history)
    expect(result.window_games).toBe(history.length)
    expect(result.form_average).toBeCloseTo(formAverage(history), 9)
  })

  it('keeps a proven history in play without letting it lead', () => {
    // Two seasons ago this player averaged 90; last season 1-18. The old
    // season still lifts the read above last season's own weighted form, but
    // last season dominates it.
    const result = run(history)
    const lastOnly = formAverage(lastSeason)
    expect(result.form_average).toBeGreaterThan(lastOnly)
    expect(result.form_average).toBeLessThan((lastOnly + 90) / 2)
  })

  it("adds a player's first game of the new season to the end of the list", () => {
    const withOpener = [...history, game(2026, 1, 100)]
    const result = run(withOpener)
    expect(result.window_games).toBe(withOpener.length)
    expect(result.form_average).toBeCloseTo(formAverage(withOpener), 9)
    expect(result.form_average).toBeGreaterThan(run(history).form_average)

    const season = result.hit_rates.find((r) => r.window === 'season')
    expect(season?.season).toBe(2026)
    expect(season?.games).toBe(1)
  })

  it('works out the same whatever order the games arrive in', () => {
    const ordered = [...history, game(2026, 1, 100)]
    expect(run([...ordered].reverse()).form_average).toBeCloseTo(run(ordered).form_average, 9)
  })
})
