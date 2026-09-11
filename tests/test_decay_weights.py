"""Offseason-aware recency weighting, for both the ensemble and the ridge model.

A game's age is how many games back it is plus OFFSEASON_GAP_GAMES for every
offseason in between. These pin that rule, and - most importantly - that the
ridge model computes its features identically at training time (a column over
history) and at prediction time (one row for the next game). Features that
differ between the two are how a model that validated well goes quietly wrong.
"""

import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ml_model  # noqa: E402
from core.projection_models import (  # noqa: E402
    HALF_LIFE_GAMES, OFFSEASON_GAP_GAMES, decay_weights, recency_weights,
)


def test_single_season_is_plain_recency_weighting():
    assert np.allclose(decay_weights([2025] * 7), recency_weights(7, HALF_LIFE_GAMES))


def test_last_season_counts_as_if_it_were_further_back():
    seasons = [2025] * 5 + [2026]
    with_gap = decay_weights(seasons)
    without = decay_weights(seasons, gap=0.0)
    # The same games, but last season's share shrinks once the offseason counts.
    assert with_gap[:5].sum() < without[:5].sum()
    # Adjacent games in the same season keep the plain half-life ratio...
    assert with_gap[3] / with_gap[4] == pytest.approx(0.5 ** (1 / HALF_LIFE_GAMES))
    # ...and the step across the offseason is the gap on top of one game.
    assert with_gap[4] / with_gap[5] == pytest.approx(0.5 ** ((1 + OFFSEASON_GAP_GAMES) / HALF_LIFE_GAMES))


def test_weights_are_a_distribution():
    w = decay_weights([2019] * 17 + [2020] * 17 + [2026] * 2)
    assert w.sum() == pytest.approx(1.0)
    assert np.all(np.diff(w) > 0)  # strictly newer means strictly heavier


def _frame():
    rows = []
    for name, seasons in (('A', [2024] * 6 + [2025] * 5), ('B', [2025] * 4 + [2026] * 2)):
        for i, s in enumerate(seasons):
            rows.append({'player_display_name': name, 'season': s, 'week': i + 1,
                         'receiving_yards': float(10 * i + (7 if name == 'B' else 0))})
    return pd.DataFrame(rows).sort_values(['season', 'week', 'player_display_name']).reset_index(drop=True)


def test_training_ewma_without_a_gap_is_pandas_ewm():
    frame = _frame()
    ours = ml_model._prior_ewma(frame, 'receiving_yards', 3.0, gap=0.0)
    pandas = frame.groupby('player_display_name')['receiving_yards'].transform(
        lambda s: s.shift(1).ewm(halflife=3.0, min_periods=1).mean())
    assert np.allclose(ours, pandas, equal_nan=True)


def test_training_ewma_matches_decay_weights_across_an_offseason():
    frame = _frame()
    ours = ml_model._prior_ewma(frame, 'receiving_yards', 8.0)
    a = frame[frame.player_display_name == 'A'].reset_index()
    j = len(a) - 1  # A's last game: every earlier game, two seasons, is its history
    prior = a.iloc[:j]
    expected = np.dot(prior['receiving_yards'], decay_weights(prior['season'], half_life=8.0))
    assert ours[a.loc[j, 'index']] == pytest.approx(expected)


def test_prediction_features_equal_training_features_for_the_same_history():
    """features_for_next_game must reproduce what _prior_ewma would give a next row."""
    history = _frame()
    history = history[history.player_display_name == 'B'].assign(position='WR', opponent_team='SEA',
                                                                  targets=[3.0, 5.0, 4.0, 6.0, 2.0, 7.0],
                                                                  receptions=[2.0, 4.0, 3.0, 5.0, 1.0, 5.0])
    next_row = history.iloc[[-1]].assign(week=99, receiving_yards=0.0, targets=0.0, receptions=0.0)
    extended = pd.concat([history, next_row], ignore_index=True)
    features = ['form_short', 'form_long', 'usage_targets_short', 'usage_receptions_long']
    columns = {'form_short': ('receiving_yards', 3), 'form_long': ('receiving_yards', 8),
               'usage_targets_short': ('targets', 3), 'usage_receptions_long': ('receptions', 8)}
    trained = {f: ml_model._prior_ewma(extended, col, h).iloc[-1] for f, (col, h) in columns.items()}

    stub = mock.Mock(features=features)
    with mock.patch.object(ml_model, 'load_career_data', return_value=history), \
            mock.patch.object(ml_model, 'calendar_season', return_value=2026), \
            mock.patch('core.monte_carlo_sim.position_allowed', return_value=float('nan')):
        served = ml_model.features_for_next_game('B', 'SEA', 'receiving_yards', stub)[0]

    assert np.allclose(served, [trained[f] for f in features])
