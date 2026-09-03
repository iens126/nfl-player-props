"""Tests for the stability/outlier maths.

The outlier filter used to be able to remove every row: with only a game or
two the standard deviation is zero, every z-score comes out NaN, and the
`< threshold` comparison drops the lot. determine_stability then indexed into
an empty frame, so /api/players/{name} returned a 500 for eight real players.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stats_utils import (  # noqa: E402
    determine_stability, remove_outliers, stability_rating,
)


def _games(values, name='Test Player'):
    return pd.DataFrame({
        'player_display_name': [name] * len(values),
        'week': list(range(1, len(values) + 1)),
        'receiving_yards': values,
        'receptions': [max(1, int(v / 10)) for v in values],
    })


def test_single_game_does_not_empty_the_frame():
    df = _games([50.0])
    assert len(remove_outliers(df, cols=['receiving_yards'])) == 1


def test_identical_games_do_not_empty_the_frame():
    """Zero variance makes every z-score NaN - that must not drop everything."""
    df = _games([40.0, 40.0, 40.0])
    assert len(remove_outliers(df, cols=['receiving_yards'])) == 3


def test_genuine_outliers_are_still_removed():
    df = _games([40.0, 42.0, 41.0, 39.0, 43.0, 40.0, 41.0, 300.0])
    cleaned = remove_outliers(df, cols=['receiving_yards'], z_thresh=2.0)
    assert len(cleaned) < len(df)
    assert 300.0 not in cleaned['receiving_yards'].values


def test_stability_survives_a_one_game_player():
    name, summary = determine_stability(_games([50.0]))
    assert name == 'Test Player'
    assert isinstance(summary, pd.DataFrame)


def test_stability_survives_identical_games():
    name, summary = determine_stability(_games([40.0, 40.0, 40.0]))
    assert name == 'Test Player'


@pytest.mark.parametrize('count', range(1, 9))
def test_stability_never_raises_for_short_careers(count):
    values = [40.0 + i for i in range(count)]
    determine_stability(_games(values))


def test_empty_input_is_rejected_clearly():
    with pytest.raises(ValueError, match='without any games'):
        determine_stability(_games([]))


def test_stability_rating_buckets():
    assert stability_rating(0.20) == 'HIGH'
    assert stability_rating(0.50) == 'MEDIUM'
    assert stability_rating(0.90) == 'LOW'
    assert stability_rating(None) is None
    assert stability_rating(np.nan) is None
