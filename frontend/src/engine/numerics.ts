/**
 * Special functions the projection models need and JavaScript doesn't have.
 *
 * Python's `math` module supplies `erfc` and `lgamma` from libm; the browser
 * supplies neither, so they're implemented here. Both are standard, long-lived
 * approximations, and `engine.test.ts` checks them against values produced by
 * Python so the ported models can't quietly disagree with the Python engine
 * they were derived from.
 */

const LANCZOS_G = 7
const LANCZOS_COEFFICIENTS = [
  0.99999999999980993, 676.5203681218851, -1259.1392167224028,
  771.32342877765313, -176.61502916214059, 12.507343278686905,
  -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
]

/** Natural log of the gamma function (Lanczos approximation). */
export function lgamma(x: number): number {
  if (x < 0.5) {
    // Reflection formula, for the range where Lanczos is inaccurate.
    return Math.log(Math.PI / Math.sin(Math.PI * x)) - lgamma(1 - x)
  }
  const z = x - 1
  let a = LANCZOS_COEFFICIENTS[0]
  const t = z + LANCZOS_G + 0.5
  for (let i = 1; i < LANCZOS_G + 2; i++) a += LANCZOS_COEFFICIENTS[i] / (z + i)
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(a)
}

/**
 * Complementary error function.
 *
 * Coefficients are written in their exact double representation; the published
 * table carries a digit or two more than a 64-bit float can hold, and spelling
 * them out as they will actually be stored keeps what the code says and what
 * it computes the same thing.
 *
 * Numerical Recipes' `erfc` via a Chebyshev fit — accurate to about 1.2e-7
 * across the whole real line, which is far finer than any probability this app
 * displays (it rounds to a tenth of a percent).
 */
export function erfc(x: number): number {
  const z = Math.abs(x)
  const t = 2 / (2 + z)
  const y = 4 * t - 2
  const coefficients = [
    -1.3026537197817094, 0.6419697923564902, 0.019476473204185836,
    -0.00956151478680863, -0.000946595344482036, 0.000366839497852761,
    4.2523324806907e-05, -2.0278578112534e-05, -1.624290004647e-06,
    1.30365583558e-06, 1.5626441722e-08, -8.5238095915e-08,
    6.529054439e-09, 5.059343495e-09, -9.91364156e-10,
    -2.27365122e-10, 9.6467911e-11, 2.394038e-12,
    -6.886027e-12, 8.94487e-13, 3.13092e-13,
    -1.12708e-13, 3.81e-16, 7.106e-15,
  ]

  let d = 0
  let dd = 0
  for (let j = coefficients.length - 1; j > 0; j--) {
    const tmp = d
    d = y * d - dd + coefficients[j]
    dd = tmp
  }
  const ans = t * Math.exp(-z * z + 0.5 * (coefficients[0] + y * d) - dd)
  return x >= 0 ? ans : 2 - ans
}

/** P(Z >= z) for a standard normal. */
export function normalSf(z: number): number {
  return 0.5 * erfc(z / Math.SQRT2)
}

/** Clamp into [lo, hi]. */
export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(Math.max(value, lo), hi)
}

/** Mean of a numeric array; 0 for an empty one. */
export function mean(values: number[]): number {
  if (values.length === 0) return 0
  return values.reduce((a, b) => a + b, 0) / values.length
}

/**
 * Linear-interpolated quantile, matching numpy's default ("linear") method so
 * residual percentile lookups agree with the Python side that produced them.
 */
export function quantileFromSorted(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0
  if (sorted.length === 1) return sorted[0]
  const pos = clamp(q, 0, 1) * (sorted.length - 1)
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}
