/**
 * Parity between the browser engine and the Python engine it was ported from.
 *
 * The static rebuild moved the projection maths from a Python server into the
 * browser. A port like that can go quietly wrong — same shapes, subtly
 * different numbers — so scripts/precompute.py emits golden fixtures straight
 * from the Python implementation, and this replays them here.
 *
 * If these fail, the port has drifted. Fix the TypeScript, or change the
 * Python first and regenerate the bundle.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeAll, describe, expect, it } from 'vitest'

import type { Aggregates, GameRow, ModelsFile } from './bundle'
import { project } from './projection'

const DATA = join(__dirname, '../../public/data')
const read = (p: string) => JSON.parse(readFileSync(join(DATA, p), 'utf8'))

const slug = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '')

interface Fixture {
  player: string
  stat: string
  opponent: string
  line: number
  expected: {
    projection: number
    prob_over: number
    weight: number
    form_average: number
    alternatives: Record<string, number>
    hit_rates: { window: string; games: number; hits: number; rate: number }[]
  }
}

let aggregates: Aggregates
let models: ModelsFile
let fixtures: Fixture[]
const gamesCache = new Map<string, GameRow[]>()

function gamesFor(player: string): GameRow[] {
  const key = slug(player)
  if (!gamesCache.has(key)) {
    gamesCache.set(key, read(`players/${key}.json`).games as GameRow[])
  }
  return gamesCache.get(key)!
}

beforeAll(() => {
  aggregates = read('aggregates.json')
  models = read('models.json')
  fixtures = read('fixtures.json').cases
})

describe('projection parity with the Python engine', () => {
  it('has fixtures to check against', () => {
    expect(fixtures.length).toBeGreaterThan(50)
  })

  it('matches Python on every fixture', () => {
    const failures: string[] = []

    for (const fixture of fixtures) {
      const result = project({
        player: fixture.player,
        opponent: fixture.opponent,
        stat: fixture.stat,
        line: fixture.line,
        model: 'ensemble',
        games: gamesFor(fixture.player),
        aggregates,
        models,
      })

      const where = `${fixture.player} / ${fixture.stat} / ${fixture.opponent} @ ${fixture.line}`
      const check = (label: string, actual: number, expected: number, tolerance = 1e-6) => {
        if (!Number.isFinite(actual) || Math.abs(actual - expected) > tolerance) {
          failures.push(`${where} — ${label}: got ${actual}, expected ${expected}`)
        }
      }

      check('projection', result.projection, fixture.expected.projection, 1e-4)
      check('prob_over', result.prob_over, fixture.expected.prob_over, 1e-5)
      check('weight', result.weight, fixture.expected.weight, 1e-4)
      check('form_average', result.form_average, fixture.expected.form_average, 1e-4)

      for (const [model, expected] of Object.entries(fixture.expected.alternatives)) {
        if (model === 'ml') continue // checked separately — it has its own tolerance
        check(`alternatives.${model}`, result.alternatives[model], expected, 1e-5)
      }
    }

    expect(failures.slice(0, 15).join('\n')).toBe('')
    expect(failures).toHaveLength(0)
  })

  it('matches Python on hit rates', () => {
    const failures: string[] = []
    for (const fixture of fixtures) {
      const result = project({
        player: fixture.player, opponent: fixture.opponent, stat: fixture.stat,
        line: fixture.line, model: 'ensemble', games: gamesFor(fixture.player),
        aggregates, models,
      })
      const expected = fixture.expected.hit_rates
      const actual = result.hit_rates ?? []
      if (actual.length !== expected.length) {
        failures.push(`${fixture.player}/${fixture.stat}: ${actual.length} windows vs ${expected.length}`)
        continue
      }
      for (let i = 0; i < expected.length; i++) {
        if (actual[i].window !== expected[i].window
          || actual[i].games !== expected[i].games
          || actual[i].hits !== expected[i].hits) {
          failures.push(
            `${fixture.player}/${fixture.stat} ${expected[i].window}: `
            + `got ${actual[i].hits}/${actual[i].games}, expected ${expected[i].hits}/${expected[i].games}`,
          )
        }
      }
    }
    expect(failures.slice(0, 10).join('\n')).toBe('')
  })

  it('matches Python on the trained model where it applies', () => {
    const failures: string[] = []
    let checked = 0
    for (const fixture of fixtures) {
      const expected = fixture.expected.alternatives.ml
      if (expected === undefined) continue
      const result = project({
        player: fixture.player, opponent: fixture.opponent, stat: fixture.stat,
        line: fixture.line, model: 'ensemble', games: gamesFor(fixture.player),
        aggregates, models,
      })
      const actual = result.alternatives.ml
      checked++
      // Residuals ship downsampled to percentiles, so allow a little slack.
      if (actual === undefined || Math.abs(actual - expected) > 0.02) {
        failures.push(`${fixture.player}/${fixture.stat}: ml ${actual} vs ${expected}`)
      }
    }
    expect(checked).toBeGreaterThan(0)
    expect(failures.slice(0, 10).join('\n')).toBe('')
  })
})
