/**
 * The projection pipeline, ported from core/projection.py and
 * core/monte_carlo_sim.create_weight.
 *
 * Given a player's game log and the precomputed league aggregates, this
 * reproduces what the Python engine returned: a recency-weighted window, a
 * matchup adjustment, every model's read on the line, and the hit rates.
 *
 * Parity with Python is enforced by fixtures — see engine.test.ts.
 */

import type { HitRate, HitRateWindow, ProjectionResponse } from '../api/types'
import type { Aggregates, GameRow, ModelsFile, TrainedModelFile } from './bundle'
import { OFFSEASON_GAP_GAMES, decayWeights, runModel, weightedMoments } from './models'
import { clamp, quantileFromSorted } from './numerics'

const MODEL_KEYS = ['ensemble', 'lognormal', 'negbin', 'empirical', 'triangular'] as const

/**
 * A model's P(over) through its calibration map, as core/calibration.py
 * apply_map() does it: p' = sigmoid(a * logit(p) + b). No map, no change.
 */
export function calibrated(models: ModelsFile, stat: string, key: string, p: number): number {
  const ab = models.calibration?.[stat]?.[key]
  if (!ab) return p
  const q = clamp(p, 1e-4, 1 - 1e-4)
  const z = ab[0] * Math.log(q / (1 - q)) + ab[1]
  return 1 / (1 + Math.exp(-z))
}

/** Sample standard deviation (pandas .std() default, ddof=1). */
function sampleStd(values: number[]): number {
  if (values.length < 2) return NaN
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  const ss = values.reduce((acc, v) => acc + (v - mean) ** 2, 0)
  return Math.sqrt(ss / (values.length - 1))
}

function statValues(games: GameRow[], stat: string): number[] {
  return games
    .map((g) => g[stat])
    .filter((v): v is number => typeof v === 'number' && !Number.isNaN(v))
}

/**
 * The player's rolling form — their last `rollingGames` games, across seasons.
 * Mirrors find_player(): last season's games stay in the list until this
 * season's push them out, one game at a time, so nobody starts September with
 * an empty history.
 */
function formGames(games: GameRow[], rollingGames: number): GameRow[] {
  return chronological(games).slice(-rollingGames)
}

function chronological(games: GameRow[]): GameRow[] {
  return [...games].sort((a, b) => Number(a.season) - Number(b.season) || Number(a.week) - Number(b.week))
}

/**
 * The matchup adjustment, ported from create_weight().
 *
 * Quarterbacks are scored against the opponent's team-level pass/run defense
 * relative to the league; skill players against what that defense allows to
 * players of the same depth-chart rank. Both paths read only from precomputed
 * aggregates, which is why they fit in the browser.
 */
export function createWeight(
  games: GameRow[],
  opponent: string,
  stat: string,
  aggregates: Aggregates,
): number {
  const { constants } = aggregates
  const form = formGames(games, constants.rolling_games)
  if (form.length === 0) return 0

  const position = String(form[form.length - 1].position ?? '')
  const mapping = constants.stat_map[stat]
  if (!mapping) return 0

  const playerStd = sampleStd(statValues(form, stat))
  let weight: number

  if (position === 'QB') {
    const k = constants.position_k.QB
    const league = aggregates.league_team_stats[stat]
    const defense = aggregates.defense_weekly[opponent]
    if (!league || !defense || !league.std) return 0

    const rows = mapping[1] === 'pass' ? defense.pass : defense.run
    const allowed = rows.map((r) => r[stat]).filter((v) => typeof v === 'number' && !Number.isNaN(v))
    if (allowed.length === 0) return 0

    const teamAvg = allowed.reduce((a, b) => a + b, 0) / allowed.length
    const zDefense = (teamAvg - league.mean) / league.std
    weight = k * playerStd * -zDefense
  } else {
    // Position-level, scaled by how much of the gap actually repeats. This
    // replaced a depth-chart-rank comparison that measured out as noise; see
    // core/monte_carlo_sim.py for the numbers.
    const k = constants.position_k[position] ?? constants.default_k
    const leagueAvg = aggregates.position_allowed[`NFL|${position}|${stat}`]
    const defenseAvg = aggregates.position_allowed[`${opponent}|${position}|${stat}`]
    const reliability = aggregates.signal_reliability[`${position}|${stat}`]
    if (leagueAvg == null || defenseAvg == null || reliability == null) return 0

    weight = k * reliability * (defenseAvg - leagueAvg)
  }

  return Number.isFinite(weight) ? weight : 0
}

// ---------------------------------------------------------------------------
// Hit rates
// ---------------------------------------------------------------------------

/**
 * How often the player actually reached the line, over several lookbacks.
 *
 * Counted from the game log rather than modelled — the most directly checkable
 * thing on the page.
 */
export function hitRates(games: GameRow[], stat: string, line: number): HitRate[] {
  const values = games.map((g) => {
    const v = g[stat]
    return typeof v === 'number' && !Number.isNaN(v) ? v : 0
  })
  // "Season" means this player's most recent season, which for someone who
  // hasn't played this year is not the league's current one. Matches the
  // Python, which reads the max season off the player's own career.
  const latestSeason = games.reduce((max, g) => Math.max(max, Number(g.season) || 0), 0)
  const seasonMask = games.map((g) => Number(g.season) === latestSeason)

  const windows: [HitRateWindow, number | null][] = [
    ['last_3', 3], ['last_5', 5], ['last_10', 10], ['season', null], ['career', null],
  ]

  const out: HitRate[] = []
  for (const [key, size] of windows) {
    let sample: number[]
    if (key === 'career') sample = values
    else if (key === 'season') sample = values.filter((_, i) => seasonMask[i])
    else sample = values.slice(-(size as number))

    if (sample.length === 0) continue
    const hits = sample.filter((v) => v >= line).length
    out.push({
      window: key,
      games: sample.length,
      hits,
      rate: hits / sample.length,
      average: sample.reduce((a, b) => a + b, 0) / sample.length,
      // Which season "season" is, so the panel can say so.
      ...(key === 'season' ? { season: latestSeason } : {}),
    })
  }
  return out
}

// ---------------------------------------------------------------------------
// Trained model inference
// ---------------------------------------------------------------------------

/**
 * The offseason-aware EWMA the trained model learned from (_prior_ewma), seen
 * from the next game: a game's age is games back plus OFFSEASON_GAP_GAMES for
 * every offseason in between. With no gap this is pandas' ewm(halflife).
 */
function ewmaLast(values: number[], seasons: number[], halfLife: number): number {
  if (values.length === 0) return 0
  const last = seasons[seasons.length - 1]
  let numerator = 0
  let denominator = 0
  for (let i = 0; i < values.length; i++) {
    const age = values.length - 1 - i + OFFSEASON_GAP_GAMES * (last - seasons[i])
    const weight = Math.pow(0.5, age / halfLife)
    numerator += weight * values[i]
    denominator += weight
  }
  return numerator / denominator
}

function mlFeatures(
  games: GameRow[], opponent: string, stat: string, model: TrainedModelFile, aggregates: Aggregates,
): number[] | null {
  const values = games.map((g) => {
    const v = g[stat]
    return typeof v === 'number' && !Number.isNaN(v) ? v : 0
  })
  if (values.length === 0) return null

  const last = games[games.length - 1]
  const seasons = games.map((g) => Number(g.season))
  const position = String(last.position ?? '')
  // The next game's week: a player last seen in an earlier season opens this
  // one in week 1, not week 19. Mirrors features_for_next_game().
  const nextWeek = Number(last.season) < aggregates.constants.current_season ? 1 : Number(last.week) + 1

  const row: Record<string, number> = {
    form_short: ewmaLast(values, seasons, 3),
    form_long: ewmaLast(values, seasons, 8),
    career_avg: values.reduce((a, b) => a + b, 0) / values.length,
    career_std: values.length > 1 ? sampleStd(values) : 0,
    games_played: values.length,
    week: nextWeek,
  }

  // What this defense allowed to the player's position over its last
  // rolling_games games, across seasons — the number the matchup weight reads.
  const allowed = aggregates.position_allowed[`${opponent}|${position}|${stat}`]
  row.def_allowed = typeof allowed === 'number' ? allowed : row.career_avg

  for (const column of aggregates.constants.usage_columns[stat] ?? []) {
    const usage = games.map((g) => {
      const v = g[column]
      return typeof v === 'number' && !Number.isNaN(v) ? v : 0
    })
    row[`usage_${column}_short`] = ewmaLast(usage, seasons, 3)
    row[`usage_${column}_long`] = ewmaLast(usage, seasons, 8)
  }

  const vector: number[] = []
  for (const feature of model.features) {
    if (!(feature in row)) return null
    vector.push(row[feature])
  }
  return vector
}

function mlPredict(model: TrainedModelFile, features: number[]): number {
  let sum = model.weights[0] // intercept
  for (let i = 0; i < features.length; i++) {
    sum += model.weights[i + 1] * ((features[i] - model.mean[i]) / model.scale[i])
  }
  return Math.max(sum, 0)
}

function residualsFor(model: TrainedModelFile, prediction: number): number[] {
  // np.digitize(prediction, bin_edges) — number of edges strictly below.
  let index = 0
  for (const edge of model.bin_edges) if (prediction >= edge) index++
  return model.residual_percentiles[clamp(index, 0, model.residual_percentiles.length - 1)]
}

function mlProbOver(model: TrainedModelFile, prediction: number, line: number): number {
  // Residuals ship as sorted percentiles, so the share of outcomes at or above
  // the line is found by locating (line - prediction) in that ladder.
  const ladder = residualsFor(model, prediction)
  const target = line - prediction
  let below = 0
  for (const r of ladder) if (r < target) below++
  return clamp(1 - below / ladder.length, 0, 1)
}

function mlSpread(model: TrainedModelFile, prediction: number): number {
  const ladder = residualsFor(model, prediction)
  const mean = ladder.reduce((a, b) => a + b, 0) / ladder.length
  return Math.sqrt(ladder.reduce((acc, r) => acc + (r - mean) ** 2, 0) / ladder.length)
}

// ---------------------------------------------------------------------------

export interface ProjectInput {
  player: string
  opponent: string
  stat: string
  line: number
  model: string
  games: GameRow[]
  aggregates: Aggregates
  models: ModelsFile
}

/** Full projection: the chosen model's read plus every alternative. */
export function project(input: ProjectInput): ProjectionResponse {
  const { player, opponent, stat, line, games, aggregates, models } = input
  const { constants } = aggregates

  if (!constants.stat_map[stat]) throw new Error(`Unsupported stat category '${stat}'`)

  // Every game the player has, weighted by age rather than cut off at a window:
  // weights halve every HALF_LIFE_GAMES games back, and each offseason in
  // between adds OFFSEASON_GAP_GAMES. Recent form leads, but a proven career
  // never drops to zero. Mirrors _window() in core/projection.py.
  const ordered = chronological(games)
  const played = ordered.filter((g) => typeof g[stat] === 'number' && !Number.isNaN(g[stat]))
  const values = played.map((g) => g[stat] as number)
  if (values.length === 0) {
    throw new Error(`Not enough recent games for ${player} to run a projection`)
  }

  const weights = decayWeights(played.map((g) => Number(g.season)))
  const shift = createWeight(ordered, opponent, stat, aggregates)
  const { mean: rawMean, ess } = weightedMoments(values, weights)

  // Every probability goes through the shipped calibration map first.
  const alternatives: Record<string, number> = {}
  for (const key of MODEL_KEYS) {
    alternatives[key] = calibrated(models, stat, key, runModel(key, values, weights, line, stat, shift).probOver)
  }

  // The trained model, when it applies to this stat and player.
  const trained = models.models[stat]
  let ml: { projection: number; probOver: number; std: number } | null = null
  if (trained) {
    const features = mlFeatures(ordered, opponent, stat, trained, aggregates)
    if (features) {
      const prediction = mlPredict(trained, features)
      ml = {
        projection: prediction,
        probOver: calibrated(models, stat, 'ml', mlProbOver(trained, prediction, line)),
        std: mlSpread(trained, prediction),
      }
      alternatives.ml = ml.probOver
    }
  }

  let projection: number
  let probOver: number
  let std: number
  let modelKey: string
  let modelLabel: string

  if (input.model === 'ml') {
    if (!ml) {
      throw new Error(
        `The trained model isn't available for ${stat} — not enough history for this player or stat.`,
      )
    }
    projection = ml.projection
    probOver = ml.probOver
    std = ml.std
    modelKey = 'ml'
    modelLabel = 'Trained ridge regression'
  } else {
    const result = runModel(input.model, values, weights, line, stat, shift)
    const calKey = input.model === 'poisson'
      ? 'negbin'
      : (MODEL_KEYS as readonly string[]).includes(input.model) ? input.model : 'ensemble'
    projection = result.projection
    probOver = calibrated(models, stat, calKey, result.probOver)
    std = result.std
    modelKey = result.model
    modelLabel = result.label
  }

  return {
    player, opponent, stat, line,
    projection,
    prob_over: probOver,
    prob_under: 1 - probOver,
    weight: shift,
    model: modelKey,
    model_label: modelLabel,
    form_average: rawMean,
    season_average: values.reduce((a, b) => a + b, 0) / values.length,
    recent_games: values.length,
    effective_games: ess,
    std_dev: std,
    window_games: values.length,
    alternatives,
    hit_rates: hitRates(ordered, stat, line),
    ml_projection: ml ? ml.projection : null,
  }
}

export { quantileFromSorted }
