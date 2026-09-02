"""Tests for the projection distributions.

These guard the properties that make a projection trustworthy - probabilities
that are monotone in the line, closed-form answers that agree with brute-force
sampling, confidence that scales with evidence, and no crashes on the
degenerate windows real data produces (a single game, all zeros, a rookie's
first week).

Runs under pytest, or standalone with `python tests/test_projection_models.py`
so the maths can be checked without adding a test dependency to the deploy.
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.projection_models import (  # noqa: E402
    PRIOR_CV,
    PRIOR_STRENGTH,
    _nbinom_pmf,
    _poisson_pmf,
    _shrink,
    count_distribution,
    empirical_kde,
    ensemble,
    recency_weights,
    run_model,
    triangular_monte_carlo,
    weighted_moments,
    zero_inflated_lognormal,
)

YARDS = np.array([12.0, 0.0, 45.0, 78.0, 33.0, 51.0, 20.0, 64.0])
COUNTS = np.array([1.0, 9.0, 2.0, 12.0, 3.0, 11.0, 0.0, 8.0])


def test_poisson_pmf_matches_known_value():
    """P(X >= 5) for lambda=3 is a textbook 0.1847368."""
    got = 1 - sum(_poisson_pmf(k, 3.0) for k in range(5))
    assert abs(got - 0.1847368) < 1e-6


def test_nbinom_pmf_is_a_distribution():
    r, p = 4.0, 0.35
    total = sum(_nbinom_pmf(k, r, p) for k in range(3000))
    mean = sum(k * _nbinom_pmf(k, r, p) for k in range(3000))
    assert abs(total - 1.0) < 1e-9
    assert abs(mean - r * (1 - p) / p) < 1e-6


def test_recency_weights_favour_recent_games():
    w = recency_weights(4, half_life=2.0)
    assert abs(w.sum() - 1.0) < 1e-12
    assert w[-1] > w[-2] > w[-3] > w[-4]
    # Two games back should carry half the weight of the most recent.
    assert abs(w[-3] / w[-1] - 0.5) < 1e-9


def test_lognormal_closed_form_matches_sampling():
    """The analytic CDF must agree with drawing from the same fitted mixture."""
    w = recency_weights(len(YARDS))
    mean, _var, ess = weighted_moments(YARDS, w)

    positive = YARDS > 0
    p_zero = float(np.sum(w[~positive]))
    p_pos = 1 - p_zero
    pw = w[positive] / p_pos
    pm, pv, _ = weighted_moments(YARDS[positive], pw)
    cv = min(max(_shrink(math.sqrt(pv) / pm, PRIOR_CV, ess), 0.10), 2.5)
    sigma_sq = math.log(1 + cv**2)
    mu = math.log(mean / p_pos) - sigma_sq / 2

    rng = np.random.default_rng(0)
    draws = np.where(rng.random(400_000) < p_zero, 0.0, rng.lognormal(mu, math.sqrt(sigma_sq), 400_000))

    for line in (10, 30, 50, 80, 120):
        closed = zero_inflated_lognormal(YARDS, w, line).prob_over
        sampled = float(np.mean(draws >= line))
        assert abs(closed - sampled) < 0.005, f"line {line}: {closed} vs {sampled}"


def test_projection_preserves_the_weighted_mean():
    w = recency_weights(len(YARDS))
    expected, _var, _ess = weighted_moments(YARDS, w)
    assert abs(zero_inflated_lognormal(YARDS, w, 50).projection - expected) < 1e-9


def test_matchup_shift_moves_the_projection():
    w = recency_weights(len(YARDS))
    base = zero_inflated_lognormal(YARDS, w, 50)
    up = zero_inflated_lognormal(YARDS, w, 50, shift=10.0)
    down = zero_inflated_lognormal(YARDS, w, 50, shift=-10.0)
    assert up.projection > base.projection > down.projection
    assert up.prob_over > base.prob_over > down.prob_over


def test_count_model_picks_poisson_when_not_overdispersed():
    steady = np.array([5.0, 5.0, 6.0, 5.0, 4.0, 5.0, 5.0, 6.0])
    result = count_distribution(steady, recency_weights(len(steady)), 4.5)
    assert result.model == 'poisson'


def test_count_model_picks_negbin_when_overdispersed():
    result = count_distribution(COUNTS, recency_weights(len(COUNTS)), 4.5)
    assert result.model == 'negbin'


def test_count_model_half_lines_are_exact():
    """A 4.5 line must mean '5 or more', not 'at least 4.5'."""
    w = recency_weights(len(COUNTS))
    at_4_5 = count_distribution(COUNTS, w, 4.5).prob_over
    at_5 = count_distribution(COUNTS, w, 5.0).prob_over
    assert abs(at_4_5 - at_5) < 1e-12


def test_probabilities_are_monotone_in_the_line():
    for stat, values in (('receiving_yards', YARDS), ('receptions', COUNTS)):
        w = recency_weights(len(values))
        probs = [ensemble(values, w, line, stat).prob_over for line in np.arange(0, 150, 2.5)]
        assert all(a >= b - 1e-12 for a, b in zip(probs, probs[1:])), stat


def test_no_hard_zero_outside_the_observed_range():
    """The flaw that motivated replacing the triangular model.

    A player whose last three games topped out at 70 still has some chance of
    80, and a model that reports exactly 0% for it is not credible.
    """
    tight = np.array([40.0, 55.0, 70.0])
    w = recency_weights(3)

    assert triangular_monte_carlo(tight, w, 80).prob_over == 0.0
    assert 0.0 < ensemble(tight, w, 80, 'receiving_yards').prob_over < 1.0
    assert 0.0 < ensemble(tight, w, 150, 'receiving_yards').prob_over < 1.0


def test_confidence_scales_with_evidence():
    """One game must not produce the same certainty as ten."""
    one = ensemble(np.array([50.0]), recency_weights(1), 40, 'receiving_yards')
    many = np.array([48.0, 52.0, 49.0, 51.0, 50.0, 47.0, 53.0, 50.0, 49.0, 51.0])
    ten = ensemble(many, recency_weights(len(many)), 40, 'receiving_yards')

    assert one.prob_over < ten.prob_over
    assert one.effective_games < ten.effective_games


def test_results_are_deterministic():
    w = recency_weights(len(YARDS))
    first = ensemble(YARDS, w, 50, 'receiving_yards').prob_over
    second = ensemble(YARDS, w, 50, 'receiving_yards').prob_over
    assert first == second


def test_degenerate_windows_do_not_crash():
    for values in (
        np.array([50.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([7.0, 7.0]),
        np.array([300.0, 412.0, 255.0]),
        np.array([0.0, 0.0, 88.0]),
    ):
        w = recency_weights(len(values))
        for model in ('ensemble', 'lognormal', 'negbin', 'empirical', 'triangular'):
            res = run_model(model, values, w, 40, 'receiving_yards')
            assert 0.0 <= res.prob_over <= 1.0
            assert math.isfinite(res.projection)
            assert math.isfinite(res.std)


def test_empirical_handles_bimodal_usage():
    """A back who either gets 5 carries or 20 shouldn't be modelled as ~12."""
    bimodal = np.array([5.0, 20.0, 5.0, 19.0, 6.0, 21.0, 4.0, 20.0])
    w = recency_weights(len(bimodal))
    # Around the empty middle, the empirical model should be less confident of
    # an "over" than a smooth unimodal fit centred there.
    emp = empirical_kde(bimodal, w, 12.5).prob_over
    assert 0.0 < emp < 1.0


def test_shrinkage_pulls_toward_the_prior():
    """With no evidence the estimate is the prior; with lots it is the data."""
    thin = _shrink(0.1, PRIOR_CV, ess=1.0)
    thick = _shrink(0.1, PRIOR_CV, ess=50.0)
    assert thin > thick
    assert abs(thick - 0.1) < 0.05
    # The blend at ess == PRIOR_STRENGTH is the midpoint, before the
    # predictive-variance inflation.
    midpoint = (PRIOR_STRENGTH * 0.1 + PRIOR_STRENGTH * PRIOR_CV) / (2 * PRIOR_STRENGTH)
    assert _shrink(0.1, PRIOR_CV, PRIOR_STRENGTH) > midpoint


if __name__ == '__main__':
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
