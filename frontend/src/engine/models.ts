/**
 * The projection models, ported from core/projection_models.py.
 *
 * These run in the browser now: the app ships a static bundle of game logs and
 * aggregates, and does the arithmetic locally rather than asking a server. The
 * Python implementations remain the source of truth — scripts/precompute.py
 * emits golden fixtures from them, and engine.test.ts replays those fixtures
 * against this file, so the two cannot drift apart silently.
 *
 * Keep this a direct translation. If the maths needs to change, change the
 * Python first, regenerate fixtures, then mirror it here.
 */

import { clamp, lgamma, mean as arrayMean, normalSf } from './numerics'

export const HALF_LIFE_GAMES = 3.0
export const MAX_WINDOW = 10

export const PRIOR_CV = 0.7
export const PRIOR_DISPERSION = 1.3
export const PRIOR_STRENGTH = 2.0

const EPS = 1e-9

export const COUNT_STATS = new Set([
  'passing_tds', 'receiving_tds', 'rushing_tds',
  'receptions', 'targets', 'carries',
  'completions', 'attempts', 'passing_interceptions',
])

export type ModelKey = 'ensemble' | 'lognormal' | 'negbin' | 'empirical' | 'triangular' | 'ml'

export interface ModelResult {
  probOver: number
  projection: number
  std: number
  model: string
  label: string
  effectiveGames: number
}

/** Exponential-decay weights for `n` games ordered oldest -> newest. */
export function recencyWeights(n: number, halfLife = HALF_LIFE_GAMES): number[] {
  if (n <= 0) return []
  const raw: number[] = []
  for (let i = 0; i < n; i++) {
    const age = n - 1 - i // most recent game has age 0
    raw.push(Math.pow(0.5, age / Math.max(halfLife, EPS)))
  }
  const total = raw.reduce((a, b) => a + b, 0)
  return raw.map((w) => w / total)
}

export interface Moments {
  mean: number
  variance: number
  ess: number
}

/** Weighted mean, variance, and Kish effective sample size. */
export function weightedMoments(values: number[], weights: number[]): Moments {
  let mean = 0
  let sumSquares = 0
  for (let i = 0; i < values.length; i++) {
    mean += values[i] * weights[i]
    sumSquares += weights[i] * weights[i]
  }
  const ess = values.length ? 1 / sumSquares : 0
  if (values.length < 2 || ess <= 1) {
    return { mean, variance: 0, ess: Math.max(ess, 1) }
  }
  let variance = 0
  for (let i = 0; i < values.length; i++) {
    variance += weights[i] * (values[i] - mean) ** 2
  }
  variance *= ess / (ess - 1)
  return { mean, variance: Math.max(variance, 0), ess }
}

function shiftedMean(mean: number, shift: number, floor: number): number {
  return Math.max(mean + shift, floor)
}

/** Pull a spread estimate toward the league-typical prior when history is thin. */
function shrink(observed: number, prior: number, ess: number): number {
  const blended = (ess * observed + PRIOR_STRENGTH * prior) / (ess + PRIOR_STRENGTH)
  return blended * Math.sqrt(1 + 1 / Math.max(ess, 1))
}

// ---------------------------------------------------------------------------

/** Yardage as a lognormal body plus an explicit "held to zero" spike. */
export function zeroInflatedLognormal(
  values: number[], weights: number[], line: number, shift = 0,
): ModelResult {
  const { mean, ess } = weightedMoments(values, weights)
  const targetMean = shiftedMean(mean, shift, 0.1)

  let pZero = 0
  const posValues: number[] = []
  const posWeightsRaw: number[] = []
  for (let i = 0; i < values.length; i++) {
    if (values[i] > 0) {
      posValues.push(values[i])
      posWeightsRaw.push(weights[i])
    } else {
      pZero += weights[i]
    }
  }
  const pPos = 1 - pZero

  if (pPos <= EPS) {
    return {
      probOver: line <= 0 ? 1 : 0, projection: targetMean, std: 0,
      model: 'lognormal', label: 'Zero-inflated lognormal', effectiveGames: ess,
    }
  }

  const posWeights = posWeightsRaw.map((w) => w / pPos)
  const positive = weightedMoments(posValues, posWeights)
  let cv = positive.mean > EPS ? Math.sqrt(positive.variance) / positive.mean : PRIOR_CV
  cv = clamp(shrink(cv, PRIOR_CV, ess), 0.1, 2.5)

  const bodyMean = targetMean / pPos
  const sigmaSq = Math.log(1 + cv * cv)
  const sigma = Math.sqrt(sigmaSq)
  const mu = Math.log(bodyMean) - sigmaSq / 2

  const probOver = line <= 0 ? 1 : pPos * normalSf((Math.log(line) - mu) / sigma)
  const secondMoment = pPos * Math.exp(2 * mu + 2 * sigmaSq)
  const std = Math.sqrt(Math.max(secondMoment - targetMean * targetMean, 0))

  return {
    probOver: clamp(probOver, 0, 1), projection: targetMean, std,
    model: 'lognormal', label: 'Zero-inflated lognormal', effectiveGames: ess,
  }
}

function nbinomPmf(k: number, r: number, p: number): number {
  const logPmf = lgamma(k + r) - lgamma(r) - lgamma(k + 1)
    + r * Math.log(p) + k * Math.log1p(-p)
  return Math.exp(logPmf)
}

function poissonPmf(k: number, lam: number): number {
  return Math.exp(k * Math.log(lam) - lam - lgamma(k + 1))
}

/** Discrete counting stats: negative binomial, collapsing to Poisson when tight. */
export function countDistribution(
  values: number[], weights: number[], line: number, shift = 0,
): ModelResult {
  const { mean, variance, ess } = weightedMoments(values, weights)
  const targetMean = shiftedMean(mean, shift, 0.02)

  // "over 4.5" means 5+; "over 4" keeps the original >= semantics.
  const threshold = Math.abs(line - Math.round(line)) > EPS ? Math.ceil(line) : Math.round(line)
  if (threshold <= 0) {
    return {
      probOver: 1, projection: targetMean, std: Math.sqrt(Math.max(variance, 0)),
      model: 'negbin', label: 'Negative binomial', effectiveGames: ess,
    }
  }

  let ratio = mean > EPS ? variance / mean : PRIOR_DISPERSION
  ratio = shrink(ratio, PRIOR_DISPERSION, ess)
  const targetVar = Math.max(targetMean * ratio, targetMean)

  let cdfBelow = 0
  let std: number
  let model: string
  let label: string

  if (targetVar <= targetMean * 1.02) {
    const lam = targetMean
    for (let k = 0; k < threshold; k++) cdfBelow += poissonPmf(k, lam)
    std = Math.sqrt(lam)
    model = 'poisson'
    label = 'Poisson'
  } else {
    let p = targetMean / targetVar
    let r = (targetMean * targetMean) / (targetVar - targetMean)
    p = clamp(p, EPS, 1 - EPS)
    r = Math.max(r, EPS)
    for (let k = 0; k < threshold; k++) cdfBelow += nbinomPmf(k, r, p)
    std = Math.sqrt(targetVar)
    model = 'negbin'
    label = 'Negative binomial'
  }

  return {
    probOver: clamp(1 - cdfBelow, 0, 1), projection: targetMean, std,
    model, label, effectiveGames: ess,
  }
}

/** The player's own games, smoothed — assumes no distributional shape. */
export function empiricalKde(
  values: number[], weights: number[], line: number, shift = 0,
): ModelResult {
  const { mean, variance, ess } = weightedMoments(values, weights)
  const targetMean = shiftedMean(mean, shift, 0)
  const std = Math.sqrt(Math.max(variance, 0))

  const bandwidth = Math.max(
    0.9 * std * Math.pow(Math.max(ess, 1), -0.2),
    Math.max(0.05 * Math.abs(mean), 0.5),
  )

  const offset = targetMean - mean
  let probOver = 0
  for (let i = 0; i < values.length; i++) {
    probOver += weights[i] * normalSf((line - (values[i] + offset)) / bandwidth)
  }

  return {
    probOver: clamp(probOver, 0, 1), projection: targetMean,
    std: Math.sqrt(std * std + bandwidth * bandwidth),
    model: 'empirical', label: 'Smoothed empirical', effectiveGames: ess,
  }
}

/**
 * The original method's triangular shape over (min, mean, max).
 *
 * Evaluated through the CDF rather than by sampling, which is what makes it
 * expressible here at all — reproducing numpy's generator in JS is not
 * practical, and the closed form is exact anyway.
 */
export function triangular(
  values: number[], weights: number[], line: number, shift = 0,
): ModelResult {
  const a = Math.min(...values)
  let b = Math.max(...values)
  if (b <= a) b = a + 1e-6
  const c = clamp(arrayMean(values), a, b)

  const x = line - shift
  let probOver: number
  if (x <= a) probOver = 1
  else if (x >= b) probOver = 0
  else if (x <= c) probOver = c > a ? 1 - ((x - a) ** 2) / ((b - a) * (c - a)) : 1
  else probOver = b > c ? ((b - x) ** 2) / ((b - a) * (b - c)) : 0

  const projection = (a + b + c) / 3 + shift
  const variance = (a * a + b * b + c * c - a * b - a * c - b * c) / 18
  const { ess } = weightedMoments(values, weights)

  return {
    probOver: clamp(probOver, 0, 1), projection, std: Math.sqrt(Math.max(variance, 0)),
    model: 'triangular', label: 'Triangular (original method)', effectiveGames: ess,
  }
}

const EMPIRICAL_CROSSOVER = 6.0

/** Blend the stat-appropriate parametric model with the empirical one. */
export function ensemble(
  values: number[], weights: number[], line: number, stat: string, shift = 0,
): ModelResult {
  const parametric = COUNT_STATS.has(stat)
    ? countDistribution(values, weights, line, shift)
    : zeroInflatedLognormal(values, weights, line, shift)
  const emp = empiricalKde(values, weights, line, shift)

  const ess = parametric.effectiveGames
  const wEmp = ess / (ess + EMPIRICAL_CROSSOVER)
  const probOver = (1 - wEmp) * parametric.probOver + wEmp * emp.probOver

  return {
    probOver: clamp(probOver, 0, 1),
    projection: parametric.projection,
    std: parametric.std,
    model: 'ensemble',
    label: `Ensemble (${parametric.label} + empirical)`,
    effectiveGames: ess,
  }
}

/** Dispatch by model name; unknown names fall back to the ensemble. */
export function runModel(
  model: string, values: number[], weights: number[], line: number, stat: string, shift = 0,
): ModelResult {
  switch (model) {
    case 'lognormal': return zeroInflatedLognormal(values, weights, line, shift)
    case 'negbin':
    case 'poisson': return countDistribution(values, weights, line, shift)
    case 'empirical': return empiricalKde(values, weights, line, shift)
    case 'triangular': return triangular(values, weights, line, shift)
    default: return ensemble(values, weights, line, stat, shift)
  }
}
