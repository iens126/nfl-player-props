"""Turns a player + opponent + line into a projection.

This is the orchestration layer: it pulls the player's game log, builds the
recency-weighted window, asks core.monte_carlo_sim for the matchup adjustment,
and hands both to one of the models in core.projection_models.

The models themselves are closed-form, so a projection is a few hundred
microseconds of arithmetic rather than a 10,000-draw sampling run. That makes
it cheap enough to evaluate *every* model on every request, which is what
powers the model-consensus view - if the parametric fit and the player's own
empirical history disagree about a line, that disagreement is a genuinely
useful signal and worth showing rather than hiding behind one number.
"""

import numpy as np

from core.data_loader import find_player
from core.monte_carlo_sim import create_weight, STAT_MAP
from core.projection_models import (
    MAX_WINDOW, MODELS, DEFAULT_MODEL, recency_weights, run_model, weighted_moments,
)


def _window(name, stat_cat):
    """The player's most recent games for `stat_cat`, oldest -> newest."""
    df = find_player(name)
    if stat_cat not in df.columns:
        raise ValueError(f"'{stat_cat}' has no recorded data for {name}")

    series = df.sort_values('week')[stat_cat].dropna()
    values = series.tail(MAX_WINDOW).to_numpy(dtype=float)
    if len(values) == 0:
        raise ValueError(f"Not enough recent games for {name} to run a projection")
    return values


def project(name, def_team, stat_cat, line, model=DEFAULT_MODEL):
    """Project `stat_cat` for `name` against `def_team` and price `line`.

    Returns the chosen model's read plus every other model's over probability,
    so the caller can show how sensitive the answer is to the assumed shape.
    """
    if stat_cat not in STAT_MAP:
        raise ValueError(f"Unsupported stat category '{stat_cat}'")

    values = _window(name, stat_cat)
    weights = recency_weights(len(values))
    shift = create_weight(name, def_team, stat_cat)

    result = run_model(model, values, weights, line, stat_cat, shift)
    raw_mean, _var, ess = weighted_moments(values, weights)

    alternatives = {
        key: round(run_model(key, values, weights, line, stat_cat, shift).prob_over, 6)
        for key in MODELS
    }

    return {
        'projection': result.projection,
        'prob_over': result.prob_over,
        'prob_under': 1.0 - result.prob_over,
        'weight': shift,
        'model': result.model if model == DEFAULT_MODEL else model,
        'model_label': result.label,
        'form_average': float(raw_mean),
        'season_average': float(np.mean(values)),
        'recent_games': int(len(values)),
        'effective_games': float(ess),
        'std_dev': result.std,
        'window_games': int(len(values)),
        'alternatives': alternatives,
    }
