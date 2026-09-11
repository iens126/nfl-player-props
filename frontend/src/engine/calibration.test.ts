/**
 * The browser applies the shipped calibration maps exactly as Python does:
 * p' = sigmoid(a * logit(p) + b), per stat and model, and nothing at all when
 * the bundle carries no map. The parity fixtures check the real maps against
 * Python end to end; this pins the mechanics.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import type { Aggregates, GameRow, ModelsFile } from './bundle'
import { calibrated, project } from './projection'

const DATA = join(__dirname, '../../public/data')
const read = (p: string) => JSON.parse(readFileSync(join(DATA, p), 'utf8'))
const aggregates: Aggregates = read('aggregates.json')
const shipped: ModelsFile = read('models.json')

const games: GameRow[] = Array.from({ length: 20 }, (_, i) => ({
  season: 2025, week: i + 1, team: 'KC', opponent_team: 'DEN', position: 'WR',
  receiving_yards: 30 + (i % 7) * 8, targets: 6, receptions: 4,
}))

function run(models: ModelsFile, model = 'ensemble', line = 50.5) {
  return project({ player: 'Test', opponent: 'BAL', stat: 'receiving_yards', line, model, games, aggregates, models })
}

const logit = (p: number) => Math.log(p / (1 - p))
const sigmoid = (z: number) => 1 / (1 + Math.exp(-z))

describe('calibration maps', () => {
  const raw: ModelsFile = { ...shipped, calibration: {} }
  const shifted: ModelsFile = { ...shipped, calibration: { receiving_yards: { ensemble: [0.8, -0.2], empirical: [1, 0.5] } } }

  it('apply sigmoid(a * logit(p) + b)', () => {
    expect(calibrated(shifted, 'receiving_yards', 'ensemble', 0.6)).toBeCloseTo(sigmoid(0.8 * logit(0.6) - 0.2), 12)
  })

  it('leave a probability alone when there is no map', () => {
    expect(calibrated(raw, 'receiving_yards', 'ensemble', 0.6)).toBe(0.6)
    expect(calibrated(shifted, 'receptions', 'ensemble', 0.6)).toBe(0.6)
  })

  it('reach the headline number and every alternative, each with its own map', () => {
    const before = run(raw)
    const after = run(shifted)
    expect(after.prob_over).toBeCloseTo(sigmoid(0.8 * logit(before.prob_over) - 0.2), 9)
    expect(after.alternatives.ensemble).toBeCloseTo(after.prob_over, 12)
    expect(after.alternatives.empirical).toBeCloseTo(sigmoid(logit(before.alternatives.empirical) + 0.5), 9)
    expect(after.alternatives.lognormal).toBe(before.alternatives.lognormal)
  })

  it('never make a higher line look likelier to clear', () => {
    const ladder = [20.5, 30.5, 40.5, 50.5, 60.5, 70.5, 80.5]
    const probs = ladder.map((line) => run(shipped, 'ensemble', line).prob_over)
    for (let i = 1; i < probs.length; i++) expect(probs[i]).toBeLessThanOrEqual(probs[i - 1])
  })
})
