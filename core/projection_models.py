"""Probability models for a prop line.

Each model answers the same question - "given this player's recent games, what
is P(stat >= line)?" - but assumes a different shape for the underlying
distribution. They are pure functions of a value/weight vector so they can be
unit-tested and compared without touching nflverse data.

Why not just Monte Carlo a triangular distribution (the original approach)?

  * A triangular fitted to (min, mean, max) of a 3-game window is bounded by
    that window, so any line outside it gets a hard 0% or 100% - a projection
    that says "0.0% chance of 80 receiving yards" because the player's last
    three games topped out at 70 is not credible.
  * 3 games is a very small sample: one outlier redefines the whole shape.
  * Sampling makes results non-deterministic - the same request twice returns
    slightly different numbers, which reads as a bug to a user.
  * Sampling is also the slow way to get a number these families define in
    closed form.

So the models here are recency-weighted over a longer window, use shapes that
match how the stat actually behaves (non-negative, right-skewed, discrete
counts), and are evaluated analytically. The original triangular shape is kept
as a selectable model for comparison, but it too is now evaluated through its
CDF rather than by sampling - same distribution, exact instead of approximate,
and portable to the browser, which reproducing numpy's RNG would not be.

Every function here is pure arithmetic on a values/weights vector: no pandas,
no RNG, no I/O. That is what lets the identical maths run in the browser off a
static data bundle, checked against these implementations by golden fixtures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Recent games count for more, but older games still inform the shape: weights
# halve every `HALF_LIFE_GAMES` games back from the most recent one.
HALF_LIFE_GAMES = 3.0
MAX_WINDOW = 10

# A short window says little about a player's spread, and a model that reports
# 98% confidence off one game is worse than useless. So the observed spread is
# shrunk toward a league-typical prior, weighted by how much history there
# actually is: PRIOR_STRENGTH is roughly "how many games of evidence the prior
# is worth". PRIOR_CV sits between the app's own HIGH (0.35) and LOW (0.65)
# stability thresholds - i.e. a typical, middlingly consistent skill player.
PRIOR_CV = 0.70
PRIOR_DISPERSION = 1.30
PRIOR_STRENGTH = 2.0

# Counting stats: discrete, non-negative, often overdispersed relative to Poisson.
COUNT_STATS = frozenset({
    'passing_tds', 'receiving_tds', 'rushing_tds',
    'receptions', 'targets', 'carries',
    'completions', 'attempts', 'passing_interceptions',
})

# Yardage: continuous, non-negative, right-skewed, with genuine zero games.
CONTINUOUS_STATS = frozenset({'passing_yards', 'receiving_yards', 'rushing_yards'})

_EPS = 1e-9


@dataclass(frozen=True)
class ModelResult:
    """One model's read on a line."""
    prob_over: float
    projection: float
    std: float
    model: str
    label: str
    effective_games: float


def _normal_sf(z: float) -> float:
    """P(Z >= z) for a standard normal, via the stdlib error function."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def recency_weights(n: int, half_life: float = HALF_LIFE_GAMES) -> np.ndarray:
    """Exponential-decay weights for `n` games ordered oldest -> newest."""
    if n <= 0:
        return np.zeros(0)
    age = np.arange(n - 1, -1, -1, dtype=float)  # most recent game has age 0
    w = 0.5 ** (age / max(half_life, _EPS))
    return w / w.sum()


def weighted_moments(values: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    """Weighted (mean, variance, effective sample size).

    Effective sample size is Kish's, 1/sum(w^2) for normalized weights - it is
    what the recency weighting costs us in statistical power, and drives how
    much the ensemble trusts the empirical shape over the parametric one.
    """
    mean = float(np.sum(values * weights))
    ess = float(1.0 / np.sum(weights ** 2)) if len(values) else 0.0
    if len(values) < 2 or ess <= 1.0:
        return mean, 0.0, max(ess, 1.0)
    # Reliability-weighted variance, debiased by the effective sample size.
    var = float(np.sum(weights * (values - mean) ** 2)) * (ess / (ess - 1.0))
    return mean, max(var, 0.0), ess


def _shifted_mean(mean: float, shift: float, floor: float) -> float:
    """Apply the matchup adjustment without letting the mean go non-positive."""
    return max(mean + shift, floor)


def _shrink(observed: float, prior: float, ess: float) -> float:
    """Pull a spread estimate toward the league-typical prior when history is thin.

    Also carries the usual predictive-variance penalty: we don't know the true
    mean either, so a projection from few games should be wider than the games
    alone suggest.
    """
    blended = (ess * observed + PRIOR_STRENGTH * prior) / (ess + PRIOR_STRENGTH)
    return blended * math.sqrt(1.0 + 1.0 / max(ess, 1.0))


# ---------------------------------------------------------------------------
# Continuous yardage: zero-inflated lognormal
# ---------------------------------------------------------------------------

def zero_inflated_lognormal(
    values: np.ndarray, weights: np.ndarray, line: float, shift: float = 0.0
) -> ModelResult:
    """Yardage as a lognormal body plus an explicit "held to zero" spike.

    Yards are non-negative and right-skewed (a receiver's ceiling is much
    further from their median than their floor is), which a lognormal captures
    and a symmetric normal does not. Modelling zero games separately matters
    for low-volume players, where a real share of games are goose eggs that
    would otherwise drag the whole fitted curve toward zero.
    """
    mean, var, ess = weighted_moments(values, weights)
    target_mean = _shifted_mean(mean, shift, floor=0.1)

    positive = values > 0
    p_zero = float(np.sum(weights[~positive]))
    p_pos = 1.0 - p_zero

    if p_pos <= _EPS:
        # Every game in the window was a zero - no shape to fit.
        prob = 1.0 if line <= 0 else 0.0
        return ModelResult(prob, target_mean, 0.0, 'lognormal', 'Zero-inflated lognormal', ess)

    # Coefficient of variation comes from the non-zero games only, so the zero
    # spike doesn't get counted as "spread" twice.
    pos_w = weights[positive] / p_pos
    pos_mean, pos_var, _ = weighted_moments(values[positive], pos_w)
    cv = math.sqrt(pos_var) / pos_mean if pos_mean > _EPS else PRIOR_CV
    cv = min(max(_shrink(cv, PRIOR_CV, ess), 0.10), 2.5)

    # Match the lognormal body's mean so the mixture's mean is `target_mean`.
    body_mean = target_mean / p_pos
    sigma_sq = math.log(1.0 + cv ** 2)
    sigma = math.sqrt(sigma_sq)
    mu = math.log(body_mean) - sigma_sq / 2.0

    if line <= 0:
        prob_over = 1.0
    else:
        prob_over = p_pos * _normal_sf((math.log(line) - mu) / sigma)

    # Mixture variance: E[X^2] - E[X]^2, with E[X^2] carried by the body only.
    second_moment = p_pos * math.exp(2 * mu + 2 * sigma_sq)
    std = math.sqrt(max(second_moment - target_mean ** 2, 0.0))

    return ModelResult(
        float(np.clip(prob_over, 0.0, 1.0)), target_mean, std,
        'lognormal', 'Zero-inflated lognormal', ess,
    )


# ---------------------------------------------------------------------------
# Counting stats: negative binomial (Poisson when not overdispersed)
# ---------------------------------------------------------------------------

def _nbinom_pmf(k: int, r: float, p: float) -> float:
    log_pmf = (
        math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
        + r * math.log(p) + k * math.log1p(-p)
    )
    return math.exp(log_pmf)


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def count_distribution(
    values: np.ndarray, weights: np.ndarray, line: float, shift: float = 0.0
) -> ModelResult:
    """Receptions, targets, carries, TDs - discrete events, so model them as such.

    A negative binomial handles the overdispersion these stats almost always
    show (usage varies game to game, so the variance runs above the mean); when
    a player is steady enough that variance <= mean, it collapses to Poisson.
    Either way P(X >= line) is an exact sum over the PMF rather than a sample
    frequency, so a 4.5-reception line is answered exactly.
    """
    mean, var, ess = weighted_moments(values, weights)
    target_mean = _shifted_mean(mean, shift, floor=0.02)

    # Threshold: "over 4.5" means 5+, "over 4" keeps the original >= semantics.
    threshold = math.ceil(line) if abs(line - round(line)) > _EPS else int(round(line))
    if threshold <= 0:
        return ModelResult(1.0, target_mean, math.sqrt(max(var, 0.0)), 'negbin', 'Negative binomial', ess)

    # Preserve the observed variance-to-mean ratio when the matchup shifts the
    # mean, shrunk toward typical overdispersion when the window is short.
    ratio = var / mean if mean > _EPS else PRIOR_DISPERSION
    ratio = _shrink(ratio, PRIOR_DISPERSION, ess)
    target_var = max(target_mean * ratio, target_mean)

    if target_var <= target_mean * 1.02:
        lam = target_mean
        cdf_below = sum(_poisson_pmf(k, lam) for k in range(threshold))
        std = math.sqrt(lam)
        model, label = 'poisson', 'Poisson'
    else:
        p = target_mean / target_var
        r = target_mean ** 2 / (target_var - target_mean)
        p = min(max(p, _EPS), 1 - _EPS)
        r = max(r, _EPS)
        cdf_below = sum(_nbinom_pmf(k, r, p) for k in range(threshold))
        std = math.sqrt(target_var)
        model, label = 'negbin', 'Negative binomial'

    prob_over = float(np.clip(1.0 - cdf_below, 0.0, 1.0))
    return ModelResult(prob_over, target_mean, std, model, label, ess)


# ---------------------------------------------------------------------------
# Empirical: kernel-smoothed weighted game history
# ---------------------------------------------------------------------------

def empirical_kde(
    values: np.ndarray, weights: np.ndarray, line: float, shift: float = 0.0
) -> ModelResult:
    """The player's own games, smoothed - no assumed shape at all.

    Each past game contributes a small normal bump instead of a hard step, so
    a line that falls between two observed results gets a sensible probability
    rather than snapping to the nearest game. This is the smoothed-bootstrap
    equivalent of resampling the player's history, evaluated in closed form,
    and it is the model that can represent genuinely bimodal usage (a back who
    either gets 5 carries or 20) that no single parametric family fits.
    """
    mean, var, ess = weighted_moments(values, weights)
    target_mean = _shifted_mean(mean, shift, floor=0.0)
    std = math.sqrt(max(var, 0.0))

    # Silverman-style bandwidth, floored so a flat window still has some spread.
    bandwidth = max(0.9 * std * (max(ess, 1.0) ** -0.2), max(0.05 * abs(mean), 0.5))

    shifted = values + (target_mean - mean)
    z = (line - shifted) / bandwidth
    prob_over = float(np.sum(weights * np.array([_normal_sf(zi) for zi in z])))

    return ModelResult(
        float(np.clip(prob_over, 0.0, 1.0)), target_mean,
        math.sqrt(std ** 2 + bandwidth ** 2), 'empirical', 'Smoothed empirical', ess,
    )


# ---------------------------------------------------------------------------
# Legacy: triangular Monte Carlo (the original methodology)
# ---------------------------------------------------------------------------

def triangular(
    values: np.ndarray,
    weights: np.ndarray,
    line: float,
    shift: float = 0.0,
) -> ModelResult:
    """The original model's shape: a triangle over (min, mean, max).

    Kept selectable so the methodology this app started with stays available
    for comparison. It is now evaluated through the triangular CDF rather than
    by drawing 10,000 samples: same distribution, but exact instead of
    approximate, identical every time, and expressible in the browser without
    reproducing numpy's random number generator.

    The bounded support is inherent to the shape, so lines outside the observed
    window still resolve to 0% or 100% - which is precisely why it is no longer
    the default.
    """
    a, c, b = float(np.min(values)), float(np.mean(values)), float(np.max(values))
    if b <= a:
        b = a + 1e-6
    c = min(max(c, a), b)

    # Shifting the distribution by `shift` is the same as shifting the line back.
    x = line - shift
    if x <= a:
        prob_over = 1.0
    elif x >= b:
        prob_over = 0.0
    elif x <= c:
        prob_over = 1.0 - ((x - a) ** 2) / ((b - a) * (c - a)) if c > a else 1.0
    else:
        prob_over = ((b - x) ** 2) / ((b - a) * (b - c)) if b > c else 0.0

    mean = (a + b + c) / 3.0 + shift
    variance = (a * a + b * b + c * c - a * b - a * c - b * c) / 18.0

    _m, _v, ess = weighted_moments(values, weights)
    return ModelResult(
        float(np.clip(prob_over, 0.0, 1.0)), mean, math.sqrt(max(variance, 0.0)),
        'triangular', 'Triangular (original method)', ess,
    )


# Retained so existing imports keep working.
triangular_monte_carlo = triangular


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

# How much history it takes before the player's own empirical shape outweighs
# the parametric family. At ess == this value the two are weighted equally.
_EMPIRICAL_CROSSOVER = 6.0


def ensemble(
    values: np.ndarray, weights: np.ndarray, line: float, stat: str, shift: float = 0.0
) -> ModelResult:
    """Blend the stat-appropriate parametric model with the empirical one.

    The parametric fit is smooth and extrapolates past the observed range; the
    empirical fit knows the player's actual shape but is noisy with few games.
    Weighting by effective sample size uses whichever is more trustworthy: with
    three games it is nearly all parametric, with ten it is mostly empirical.
    """
    parametric = (
        count_distribution(values, weights, line, shift)
        if stat in COUNT_STATS
        else zero_inflated_lognormal(values, weights, line, shift)
    )
    emp = empirical_kde(values, weights, line, shift)

    ess = parametric.effective_games
    w_emp = ess / (ess + _EMPIRICAL_CROSSOVER)
    prob = (1 - w_emp) * parametric.prob_over + w_emp * emp.prob_over

    return ModelResult(
        float(np.clip(prob, 0.0, 1.0)),
        parametric.projection,
        parametric.std,
        'ensemble',
        f'Ensemble ({parametric.label} + empirical)',
        ess,
    )


MODELS = {
    'ml': 'Trained ridge regression - learned from eight seasons of game logs',
    'ensemble': 'Ensemble - parametric shape blended with the player\'s own history',
    'lognormal': 'Zero-inflated lognormal - continuous, right-skewed yardage',
    'negbin': 'Negative binomial - discrete counting stats',
    'empirical': 'Smoothed empirical - the player\'s games, no assumed shape',
    'triangular': 'Triangular - the original method, evaluated exactly',
}
DEFAULT_MODEL = 'ensemble'


def run_model(
    model: str, values: np.ndarray, weights: np.ndarray, line: float, stat: str, shift: float = 0.0
) -> ModelResult:
    """Dispatch to one model by name. Unknown names fall back to the ensemble."""
    if model == 'lognormal':
        return zero_inflated_lognormal(values, weights, line, shift)
    if model in ('negbin', 'poisson'):
        return count_distribution(values, weights, line, shift)
    if model == 'empirical':
        return empirical_kde(values, weights, line, shift)
    if model == 'triangular':
        return triangular(values, weights, line, shift)
    return ensemble(values, weights, line, stat, shift)
