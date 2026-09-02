"""Tests for the trained projection model.

The headline risk with a model like this isn't a crash, it's a silent one:
features that peek at the game they're predicting, or features computed
differently at prediction time than during training. Either produces validation
numbers that look great and predictions that are quietly worthless, so both are
checked explicitly here.

These touch real nflverse data (cached after the first load), so they are
slower than the pure-maths tests.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_loader import load_career_data  # noqa: E402
from core.ml_model import (  # noqa: E402
    _build_frame,
    _prior_ewma,
    features_for_next_game,
    get_model,
)
from core.projection import hit_rates, project  # noqa: E402

STAT = 'receiving_yards'


def test_features_never_see_the_game_they_predict():
    """The core no-leakage property, checked row by row.

    A player's form feature for game N must be computable from games 1..N-1
    alone. The cheapest way to prove that is a player whose history contains a
    single enormous outlier: the features on the outlier game itself must not
    move, while the following game's features must.
    """
    frame = pd.DataFrame({
        'player_display_name': ['A'] * 6,
        'value': [10.0, 10.0, 10.0, 1000.0, 10.0, 10.0],
    })
    ewma = _prior_ewma(frame, 'value', 3)

    # Row 3 is the 1000 - its own feature must be built from the 10s before it.
    assert ewma.iloc[3] < 20, f"leakage: the outlier informed its own feature ({ewma.iloc[3]})"
    # Row 4 comes after the outlier, so it must reflect it.
    assert ewma.iloc[4] > 100, "the outlier should affect the *next* game's feature"
    # The first row has nothing before it.
    assert pd.isna(ewma.iloc[0])


def test_training_frame_features_are_backward_looking():
    frame, features = _build_frame(STAT)
    assert len(frame) > 1000
    assert 'form_short' in features and 'def_allowed' in features

    # Pick a player with a long history and verify their first row's career
    # average is not simply their own first-game value.
    counts = frame.groupby('player_display_name').size()
    name = counts[counts > 20].index[0]
    rows = frame[frame['player_display_name'] == name].sort_values(['season', 'week'])
    later = rows.iloc[10]
    prior_games = rows.iloc[:10][STAT]
    # career_avg at row 10 should summarise the games before it, so it must sit
    # inside the range of what came before - never equal that game's own value
    # by construction.
    assert prior_games.min() <= later['career_avg'] <= prior_games.max() + 1e-6


def test_validation_is_a_time_split_not_a_shuffle():
    model = get_model(STAT)
    assert model is not None
    first_season, holdout = model.seasons
    assert holdout > first_season
    assert model.metrics['holdout_season'] == holdout
    assert model.metrics['val_rows'] > 100


def test_model_beats_the_naive_baseline():
    """It must improve on 'just use recent form', or it isn't earning its place."""
    model = get_model(STAT)
    assert model.metrics['val_mae'] <= model.metrics['baseline_mae'], (
        f"trained MAE {model.metrics['val_mae']:.3f} is worse than the "
        f"recent-form baseline {model.metrics['baseline_mae']:.3f}"
    )


def test_probabilities_are_calibrated():
    """A stated rate should land near the rate that actually occurred."""
    model = get_model(STAT)
    gap = abs(model.metrics['stated_rate'] - model.metrics['actual_rate'])
    assert gap < 0.06, f"calibration off by {gap:.3f}"
    # And it must beat always guessing the base rate.
    assert model.metrics['brier'] < 0.25


def test_prediction_features_match_the_training_definitions():
    """Train/serve skew guard: same names, same count, sane magnitudes."""
    model = get_model(STAT)
    X = features_for_next_game('Mark Andrews', 'NYJ', STAT, model)
    assert X is not None
    assert X.shape == (1, len(model.features))
    assert np.all(np.isfinite(X))

    # The form features should sit in the range of the player's real games.
    career = load_career_data()
    games = career[career['player_display_name'] == 'Mark Andrews'][STAT].fillna(0.0)
    idx = model.features.index('form_long')
    assert games.min() <= X[0, idx] <= games.max()


def test_probability_is_monotone_in_the_line():
    model = get_model(STAT)
    X = features_for_next_game('Mark Andrews', 'NYJ', STAT, model)
    prediction = float(model.predict(X)[0])
    probs = [model.prob_over(prediction, line) for line in range(0, 200, 10)]
    assert all(a >= b - 1e-12 for a, b in zip(probs, probs[1:]))
    assert 0.0 <= probs[-1] <= probs[0] <= 1.0


def test_uncertainty_grows_with_the_projection():
    """A 60-yard projection should carry more spread than a 5-yard one."""
    model = get_model(STAT)
    assert model.spread(60.0) > model.spread(5.0)


def test_predictions_are_never_negative():
    model = get_model(STAT)
    X = features_for_next_game('Mark Andrews', 'NYJ', STAT, model)
    assert float(model.predict(X)[0]) >= 0.0


# --- hit rates -------------------------------------------------------------

def test_hit_rates_count_real_games():
    rates = hit_rates('Mark Andrews', STAT, 40)
    windows = {r['window']: r for r in rates}
    assert {'last_3', 'last_5', 'last_10', 'season', 'career'} <= set(windows)

    for r in rates:
        assert 0 <= r['hits'] <= r['games']
        assert abs(r['rate'] - r['hits'] / r['games']) < 1e-9

    assert windows['last_3']['games'] == 3
    assert windows['career']['games'] > windows['season']['games']


def test_hit_rate_falls_as_the_line_rises():
    low = {r['window']: r['rate'] for r in hit_rates('Mark Andrews', STAT, 10)}
    high = {r['window']: r['rate'] for r in hit_rates('Mark Andrews', STAT, 150)}
    for window in low:
        assert low[window] >= high[window]


def test_impossible_line_is_never_cleared():
    rates = hit_rates('Mark Andrews', STAT, 100000)
    assert all(r['hits'] == 0 for r in rates)


def test_projection_exposes_ml_and_hit_rates():
    result = project('Mark Andrews', 'NYJ', STAT, 45, model='ml')
    assert result['model'] == 'ml'
    assert result['ml_projection'] is not None
    assert 'ml' in result['alternatives']
    assert len(result['hit_rates']) >= 4
    assert 0.0 <= result['prob_over'] <= 1.0


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
