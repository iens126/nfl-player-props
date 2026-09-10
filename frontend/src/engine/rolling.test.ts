/**
 * The rolling form, end to end in the browser engine.
 *
 * A player who hasn't played yet this season is projected from the end of last
 * season; the moment they play once, that game joins the end of the same list
 * and the oldest one drops out. Nothing resets at the season boundary.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import type { Aggregates, GameRow, ModelsFile } from './bundle'
import { MAX_WINDOW, recencyWeights, weightedMoments } from './models'
import { project } from './projection'

const DATA = join(__dirname, '../../public/data')
const read = (p: string) => JSON.parse(readFileSync(join(DATA, p), 'utf8'))

const aggregates: Aggregates = read('aggregates.json')
const models: ModelsFile = read('models.json')

function game(season: number, week: number, yards: number): GameRow {
  return { season, week, team: 'KC', opponent_team: 'DEN', position: 'WR', receiving_yards: yards }
}

const lastSeason = Array.from({ length: 18 }, (_, i) => game(2025, i + 1, i + 1))

function run(games: GameRow[]) {
  return project({
    player: 'Test Receiver', opponent: 'BAL', stat: 'receiving_yards', line: 10.5,
    model: 'ensemble', games, aggregates, models,
  })
}

function formAverage(values: number[]) {
  return weightedMoments(values, recencyWeights(values.length)).mean
}

describe('rolling form across a season boundary', () => {
  it('projects a player with no games this season from last season', () => {
    const result = run(lastSeason)
    const expected = lastSeason.slice(-MAX_WINDOW).map((g) => g.receiving_yards as number)

    expect(result.window_games).toBe(MAX_WINDOW)
    expect(result.form_average).toBeCloseTo(formAverage(expected), 9)
    expect(result.hit_rates.find((r) => r.window === 'season')?.season).toBe(2025)
  })

  it("adds a player's first game of the new season to the end of the list", () => {
    const withOpener = [...lastSeason, game(2026, 1, 100)]
    const result = run(withOpener)
    const expected = withOpener.slice(-MAX_WINDOW).map((g) => g.receiving_yards as number)

    expect(result.window_games).toBe(MAX_WINDOW)
    expect(expected[expected.length - 1]).toBe(100)
    expect(result.form_average).toBeCloseTo(formAverage(expected), 9)
    // The one new game pulls the form up; it doesn't replace the history.
    expect(result.form_average).toBeGreaterThan(run(lastSeason).form_average)

    const season = result.hit_rates.find((r) => r.window === 'season')
    expect(season?.season).toBe(2026)
    expect(season?.games).toBe(1)
  })

  it('works out the same whatever order the games arrive in', () => {
    const shuffled = [game(2026, 1, 100), ...lastSeason].reverse()
    expect(run(shuffled).form_average).toBeCloseTo(run([...lastSeason, game(2026, 1, 100)]).form_average, 9)
  })
})
