"""The Platt map that calibrates every model's P(over).

Offline: these check the fit and the map themselves. Whether calibration
improves real out-of-sample probabilities is a property of the data, measured
when the maps were designed (see core/calibration.py); the parity fixtures
check that the browser applies the shipped maps exactly as Python does.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.calibration import _logit, apply_map, fit_map  # noqa: E402


def _sigmoid(z):
    return 1 / (1 + np.exp(-z))


def test_recovers_a_known_overconfident_bias():
    """Raw probabilities that are too extreme and too high on overs, like the
    ones measured on 2025-26 games, are pulled back to the truth."""
    rng = np.random.default_rng(0)
    truth = rng.uniform(0.05, 0.95, 40_000)
    hits = (rng.uniform(size=truth.size) < truth).astype(float)
    a_true, b_true = 0.8, -0.2           # truth = sigmoid(0.8 * logit(raw) - 0.2)
    raw = _sigmoid((_logit(truth) - b_true) / a_true)
    a, b = fit_map(raw, hits, np.ones(raw.size))
    assert a == pytest.approx(a_true, abs=0.04)
    assert b == pytest.approx(b_true, abs=0.04)


def test_leaves_calibrated_probabilities_alone():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 40_000)
    hits = (rng.uniform(size=p.size) < p).astype(float)
    a, b = fit_map(p, hits, np.ones(p.size))
    assert a == pytest.approx(1.0, abs=0.04)
    assert b == pytest.approx(0.0, abs=0.04)


def test_weights_decide_which_lines_the_map_listens_to():
    """Two families of lines biased in opposite directions: the map should sit
    between them in proportion to the weight each family is given."""
    rng = np.random.default_rng(2)
    p = rng.uniform(0.2, 0.8, 20_000)
    over = (rng.uniform(size=p.size) < p - 0.1).astype(float)    # family A: overs overstated
    under = (rng.uniform(size=p.size) < p + 0.1).astype(float)   # family B: understated
    both = np.r_[p, p]
    hits = np.r_[over, under]
    _, b_equal = fit_map(both, hits, np.r_[np.ones(p.size), np.ones(p.size)])
    _, b_a_heavy = fit_map(both, hits, np.r_[np.full(p.size, 3.0), np.ones(p.size)])
    assert abs(b_equal) < 0.05
    assert b_a_heavy < b_equal


def test_map_is_monotone_so_higher_lines_never_look_likelier():
    ab = (0.83, -0.17)
    ladder = np.linspace(0.01, 0.99, 99)
    out = [apply_map(p, ab) for p in ladder]
    assert all(np.diff(out) > 0)


def test_no_map_means_no_change():
    assert apply_map(0.37, None) == 0.37


def test_build_calibration_maps_every_model_on_real_data(monkeypatch):
    """End to end on live data, with a reduced sample to stay quick.

    The headline models - the ensemble and the trained model - must get a map,
    and every map that is shipped must be a sane correction. This path once
    failed silently for every stat (a lookup that indexed away one of the
    trained model's own features) and once shipped a triangular map with a
    slope of 1883 - both caught here.
    """
    from core import calibration

    monkeypatch.setattr(calibration, 'CALIBRATION_ROWS', 300)
    maps = calibration.build_calibration('receptions')

    assert {'ensemble', 'ml'} <= set(maps)
    assert set(maps) <= set(calibration.SPECIFIED_MODELS) | {'ml'}
    lo, hi = calibration.SLOPE_RANGE
    for model, (a, b) in maps.items():
        assert lo <= a <= hi, f"{model}: slope {a} is a runaway fit"
        assert abs(b) <= calibration.MAX_INTERCEPT, f"{model}: intercept {b} is a runaway fit"


def test_refuses_a_runaway_fit():
    """Outcomes split perfectly by a barely-varying raw probability: the only
    'fit' is an enormous slope, which would push every probability to 0 or 1.
    That model is left raw instead."""
    p = np.r_[np.full(500, 0.45), np.full(500, 0.55)]
    hits = np.r_[np.zeros(500), np.ones(500)]
    assert fit_map(p, hits, np.ones(p.size)) is None


def test_fitted_maps_are_rounded_for_the_bundle():
    rng = np.random.default_rng(3)
    p = rng.uniform(0.1, 0.9, 5_000)
    a, b = fit_map(p, (rng.uniform(size=p.size) < p).astype(float), np.ones(p.size))
    # The bundle writer keeps 4 decimals; Python must apply the same map.
    assert a == round(a, 4) and b == round(b, 4)
