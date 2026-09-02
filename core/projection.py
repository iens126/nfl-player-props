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

import logging

import numpy as np

from core.data_loader import find_player, find_player_career
from core.ml_model import features_for_next_game, get_model
from core.monte_carlo_sim import create_weight, STAT_MAP
from core.projection_models import (
    MAX_WINDOW, MODELS, DEFAULT_MODEL, recency_weights, run_model, weighted_moments,
)

# Windows the hit-rate breakdown is reported over. "How often has he actually
# cleared this number?" is a different - and more directly checkable - question
# than what any model predicts, so it's worth showing alongside.
HIT_RATE_WINDOWS = [('last_3', 3), ('last_5', 5), ('last_10', 10), ('season', None), ('career', None)]


def hit_rates(name, stat_cat, line):
    """How often the player has reached `line`, over several lookbacks.

    Counted from actual game logs, not modelled - if a receiver has cleared 60
    yards in 4 of his last 10 and 38% of his career, that is a fact about what
    happened, and it belongs next to the projection rather than behind it.
    """
    career = find_player_career(name)
    if career.empty or stat_cat not in career.columns:
        return []

    values = career[stat_cat].fillna(0.0)
    current_season = career['season'].max()
    season_mask = (career['season'] == current_season).to_numpy()

    out = []
    for key, window in HIT_RATE_WINDOWS:
        if key == 'career':
            sample = values.to_numpy(dtype=float)
        elif key == 'season':
            sample = values.to_numpy(dtype=float)[season_mask]
        else:
            sample = values.to_numpy(dtype=float)[-window:]

        games = int(len(sample))
        if games == 0:
            continue
        hits = int(np.sum(sample >= line))
        out.append({
            'window': key,
            'games': games,
            'hits': hits,
            'rate': hits / games,
            'average': float(np.mean(sample)),
        })
    return out


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
    raw_mean, _var, ess = weighted_moments(values, weights)

    alternatives = {
        key: round(run_model(key, values, weights, line, stat_cat, shift).prob_over, 6)
        for key in MODELS
    }

    ml = _ml_projection(name, def_team, stat_cat, line)
    if ml is not None:
        alternatives['ml'] = round(ml['prob_over'], 6)

    if model == 'ml':
        if ml is None:
            raise ValueError(
                f"The trained model isn't available for {stat_cat} - not enough "
                "history for this player or stat."
            )
        projection, prob_over, std = ml['projection'], ml['prob_over'], ml['std_dev']
        model_key, model_label = 'ml', ml['label']
    else:
        result = run_model(model, values, weights, line, stat_cat, shift)
        projection, prob_over, std = result.projection, result.prob_over, result.std
        model_key = result.model if model == DEFAULT_MODEL else model
        model_label = result.label

    return {
        'projection': projection,
        'prob_over': prob_over,
        'prob_under': 1.0 - prob_over,
        'weight': shift,
        'model': model_key,
        'model_label': model_label,
        'form_average': float(raw_mean),
        'season_average': float(np.mean(values)),
        'recent_games': int(len(values)),
        'effective_games': float(ess),
        'std_dev': std,
        'window_games': int(len(values)),
        'alternatives': alternatives,
        'hit_rates': hit_rates(name, stat_cat, line),
        'ml_projection': None if ml is None else ml['projection'],
    }


def _ml_projection(name, def_team, stat_cat, line):
    """The trained model's read, or None when it can't be applied."""
    try:
        trained = get_model(stat_cat)
        if trained is None:
            return None
        features = features_for_next_game(name, def_team, stat_cat, trained)
        if features is None:
            return None
        prediction = float(trained.predict(features)[0])
        return {
            'projection': prediction,
            'prob_over': trained.prob_over(prediction, line),
            'std_dev': trained.spread(prediction),
            'label': 'Trained ridge regression',
        }
    except Exception:  # noqa: BLE001 - never let the ML path break a projection
        logging.getLogger(__name__).exception("Trained model failed for %s / %s", name, stat_cat)
        return None
