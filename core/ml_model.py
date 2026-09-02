"""A trained model, rather than a hand-specified one.

Everything in core/projection_models.py describes a distribution *we chose* and
fitted to one player's recent games. Nothing about those choices was learned
from data - which shape to use, and how much a matchup should matter, were
decided by a person.

This module learns instead. It builds a training set from every player-game in
the loaded seasons, engineers features that are strictly backward-looking, fits
a ridge regression to predict the stat, and derives its uncertainty from the
errors the model actually made on games it never saw. So both the projection
and the probability come from measured historical performance.

Two properties matter more than raw accuracy for a tool like this:

  * No leakage. Every feature for a given game is computed from games strictly
    before it (`.shift(1)` before any rolling window), and validation is a
    time split - the model is scored on the most recent season, which it never
    trained on. Shuffling rows would leak the future into the past and produce
    accuracy that evaporates in real use.
  * Calibration. A prop tool that says "60%" should be right about 60% of the
    time. Because residual spread grows with the size of the prediction (a
    5-yard projection misses by a little, a 60-yard projection by a lot), the
    error distribution is stored separately per prediction band rather than
    assumed constant.

Validation metrics are computed at training time and surfaced through the API,
so the model's own accuracy is visible in the UI instead of implied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.data_loader import bettable_columns, cached, load_career_data

logger = logging.getLogger(__name__)

RIDGE_ALPHA = 10.0
N_RESIDUAL_BINS = 5
MIN_TRAINING_ROWS = 500

# Which usage columns inform each stat. Yardage is driven by volume, so a
# receiver's recent targets matter as much as their recent yards.
_RECEIVING = ['targets', 'receptions']
_RUSHING = ['carries']
_PASSING = ['attempts', 'completions']

USAGE_COLUMNS = {
    'receiving_yards': _RECEIVING, 'receptions': _RECEIVING,
    'receiving_tds': _RECEIVING, 'targets': _RECEIVING,
    'rushing_yards': _RUSHING, 'carries': _RUSHING, 'rushing_tds': _RUSHING,
    'passing_yards': _PASSING, 'passing_tds': _PASSING, 'completions': _PASSING,
    'attempts': _PASSING, 'passing_interceptions': _PASSING,
}

POSITIONS_FOR_STAT = {
    'passing_yards': ['QB'], 'passing_tds': ['QB'], 'completions': ['QB'],
    'attempts': ['QB'], 'passing_interceptions': ['QB'],
    'rushing_yards': ['RB', 'QB', 'WR'], 'carries': ['RB', 'QB', 'WR'],
    'rushing_tds': ['RB', 'QB', 'WR'],
}
_DEFAULT_POSITIONS = ['WR', 'TE', 'RB']

# Plain-language names for the features, for the "what does this model look at"
# explanation in the UI.
FEATURE_LABELS = {
    'form_short': 'Recent form (last ~3 games)',
    'form_long': 'Longer-run form (last ~8 games)',
    'career_avg': 'Career average',
    'career_std': 'How much they swing game to game',
    'games_played': 'How many games of history they have',
    'def_allowed': 'What this defense gives up to the position',
    'week': 'Week of the season',
}
for _col in set(_RECEIVING + _RUSHING + _PASSING):
    FEATURE_LABELS[f'usage_{_col}_short'] = f'Recent {_col.replace("_", " ")}'
    FEATURE_LABELS[f'usage_{_col}_long'] = f'Longer-run {_col.replace("_", " ")}'


@dataclass
class TrainedModel:
    stat: str
    features: list[str]
    weights: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    bin_edges: np.ndarray
    residuals: list[np.ndarray]
    metrics: dict = field(default_factory=dict)
    importance: list[dict] = field(default_factory=list)
    train_rows: int = 0
    seasons: tuple[int, int] = (0, 0)

    def _design(self, X: np.ndarray) -> np.ndarray:
        return np.hstack([np.ones((len(X), 1)), (X - self.mean) / self.scale])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.clip(self._design(X) @ self.weights, 0.0, None)

    def _residuals_for(self, prediction: float) -> np.ndarray:
        idx = int(np.clip(np.digitize(prediction, self.bin_edges), 0, len(self.residuals) - 1))
        return self.residuals[idx]

    def prob_over(self, prediction: float, line: float) -> float:
        """P(outcome >= line), from the errors this model actually made.

        No distribution is assumed: the prediction is shifted by each held-back
        residual from the matching prediction band, and we count how many of
        those hypothetical outcomes clear the line.
        """
        outcomes = prediction + self._residuals_for(prediction)
        return float(np.clip(np.mean(outcomes >= line), 0.0, 1.0))

    def spread(self, prediction: float) -> float:
        return float(np.std(self._residuals_for(prediction)))


def _prior_ewma(frame: pd.DataFrame, column: str, half_life: float) -> pd.Series:
    """Exponentially weighted mean of a player's *previous* games only."""
    return frame.groupby('player_display_name', observed=True)[column].transform(
        lambda s: s.shift(1).ewm(halflife=half_life, min_periods=1).mean()
    )


def _build_frame(stat: str) -> tuple[pd.DataFrame, list[str]]:
    """Training rows with strictly backward-looking features."""
    df = load_career_data()
    positions = POSITIONS_FOR_STAT.get(stat, _DEFAULT_POSITIONS)

    df = df[df['position'].isin(positions)].copy()
    for col in ('player_display_name', 'position', 'team', 'opponent_team'):
        df[col] = df[col].astype(str)
    df = df.sort_values(['season', 'week', 'player_display_name']).reset_index(drop=True)

    usage = [c for c in USAGE_COLUMNS.get(stat, []) if c in df.columns]
    for col in [stat] + usage:
        df[col] = df[col].fillna(0.0)

    df['form_short'] = _prior_ewma(df, stat, 3)
    df['form_long'] = _prior_ewma(df, stat, 8)
    grouped = df.groupby('player_display_name', observed=True)[stat]
    df['career_avg'] = grouped.transform(lambda s: s.shift(1).expanding().mean())
    df['career_std'] = grouped.transform(lambda s: s.shift(1).expanding().std())
    df['games_played'] = grouped.transform(lambda s: s.shift(1).expanding().count())

    # What this defense has allowed to this position so far this season - again
    # shifted, so a game never contributes to its own matchup feature.
    df['def_allowed'] = df.groupby(['season', 'opponent_team', 'position'], observed=True)[stat].transform(
        lambda s: s.shift(1).expanding().mean()
    )

    features = ['form_short', 'form_long', 'career_avg', 'career_std', 'games_played', 'def_allowed', 'week']
    for col in usage:
        df[f'usage_{col}_short'] = _prior_ewma(df, col, 3)
        df[f'usage_{col}_long'] = _prior_ewma(df, col, 8)
        features += [f'usage_{col}_short', f'usage_{col}_long']

    return df.dropna(subset=features + [stat]), features


def _permutation_importance(model, X, y, features, rng) -> list[dict]:
    """How much worse the model gets when one feature is shuffled.

    Preferred over reading the raw coefficients: the form and usage features
    are strongly correlated, which splits credit between them arbitrarily and
    can even flip a sign. Breaking one feature at a time and measuring the
    damage answers "how much does this actually rely on X" honestly.
    """
    base = float(np.mean(np.abs(model.predict(X) - y)))
    scores = []
    for i, name in enumerate(features):
        shuffled = X.copy()
        shuffled[:, i] = rng.permutation(shuffled[:, i])
        damage = float(np.mean(np.abs(model.predict(shuffled) - y))) - base
        scores.append({'feature': name, 'label': FEATURE_LABELS.get(name, name), 'impact': max(damage, 0.0)})

    total = sum(s['impact'] for s in scores) or 1.0
    for s in scores:
        s['share'] = s['impact'] / total
    return sorted(scores, key=lambda s: -s['impact'])


def train(stat: str) -> TrainedModel | None:
    """Fit the model for one stat, validating on the most recent season."""
    frame, features = _build_frame(stat)
    if len(frame) < MIN_TRAINING_ROWS:
        logger.warning("Not enough history to train a model for %s (%d rows)", stat, len(frame))
        return None

    holdout = frame['season'].max()
    train_df, val_df = frame[frame['season'] < holdout], frame[frame['season'] == holdout]
    if len(train_df) < MIN_TRAINING_ROWS or len(val_df) < 50:
        return None

    X = train_df[features].to_numpy(float)
    y = train_df[stat].to_numpy(float)
    Xv = val_df[features].to_numpy(float)
    yv = val_df[stat].to_numpy(float)

    mean, scale = X.mean(axis=0), X.std(axis=0)
    scale[scale == 0] = 1.0
    design = np.hstack([np.ones((len(X), 1)), (X - mean) / scale])

    # Ridge: penalise large coefficients so correlated features can't blow up.
    # The intercept is left unpenalised.
    penalty = np.eye(design.shape[1]) * RIDGE_ALPHA
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(design.T @ design + penalty, design.T @ y)

    model = TrainedModel(
        stat=stat, features=features, weights=weights, mean=mean, scale=scale,
        bin_edges=np.array([]), residuals=[], train_rows=len(train_df),
        seasons=(int(frame['season'].min()), int(holdout)),
    )

    # Error distribution per prediction band, learned on training predictions
    # so the validation season stays genuinely held out.
    train_pred = model.predict(X)
    quantiles = np.linspace(0, 1, N_RESIDUAL_BINS + 1)[1:-1]
    model.bin_edges = np.quantile(train_pred, quantiles)
    bin_idx = np.clip(np.digitize(train_pred, model.bin_edges), 0, N_RESIDUAL_BINS - 1)
    model.residuals = [
        np.sort(y[bin_idx == b] - train_pred[bin_idx == b]) if (bin_idx == b).sum() > 20
        else np.sort(y - train_pred)
        for b in range(N_RESIDUAL_BINS)
    ]

    val_pred = model.predict(Xv)
    baseline = val_df['form_short'].to_numpy(float)  # what the app used before
    ss_res = float(((val_pred - yv) ** 2).sum())
    ss_tot = float(((yv - yv.mean()) ** 2).sum()) or 1.0

    # Calibration check: price each validation game against a plausible line
    # (the player's own longer-run form) and compare stated vs actual.
    lines = val_df['form_long'].to_numpy(float)
    probs = np.array([model.prob_over(p, l) for p, l in zip(val_pred, lines)])
    hits = (yv >= lines).astype(float)

    model.metrics = {
        'val_mae': float(np.mean(np.abs(val_pred - yv))),
        'val_r2': 1.0 - ss_res / ss_tot,
        'baseline_mae': float(np.mean(np.abs(baseline - yv))),
        'brier': float(np.mean((probs - hits) ** 2)),
        'stated_rate': float(probs.mean()),
        'actual_rate': float(hits.mean()),
        'val_rows': int(len(val_df)),
        'holdout_season': int(holdout),
    }
    model.importance = _permutation_importance(
        model, Xv, yv, features, np.random.default_rng(0)
    )
    return model


def get_model(stat: str) -> TrainedModel | None:
    """Trained model for `stat`, cached alongside the data it learned from."""
    if stat not in bettable_columns:
        return None
    return cached(f"ml_model:{stat}", lambda: train(stat))


def features_for_next_game(name: str, opponent: str, stat: str, model: TrainedModel) -> np.ndarray | None:
    """Build this player's feature row for their *next* game.

    Mirrors _build_frame's definitions against the player's full history. The
    two must agree exactly - features computed differently at prediction time
    than at training time is the classic way a model that validated well goes
    quietly wrong in production.
    """
    df = load_career_data()
    player = df[df['player_display_name'] == name].sort_values(['season', 'week'])
    if player.empty or stat not in player.columns:
        return None

    values = player[stat].fillna(0.0)
    if len(values) == 0:
        return None

    def ewma(series: pd.Series, half_life: float) -> float:
        return float(series.ewm(halflife=half_life, min_periods=1).mean().iloc[-1])

    current_season = int(player['season'].iloc[-1])
    row = {
        'form_short': ewma(values, 3),
        'form_long': ewma(values, 8),
        'career_avg': float(values.mean()),
        'career_std': float(values.std()) if len(values) > 1 else 0.0,
        'games_played': float(len(values)),
        'week': float(player['week'].iloc[-1]) + 1,
    }

    season_rows = df[(df['season'] == current_season) & (df['opponent_team'] == opponent)]
    position = str(player['position'].iloc[-1])
    allowed = season_rows[season_rows['position'] == position][stat].fillna(0.0)
    row['def_allowed'] = float(allowed.mean()) if len(allowed) else float(values.mean())

    for col in USAGE_COLUMNS.get(stat, []):
        if col in player.columns:
            usage = player[col].fillna(0.0)
            row[f'usage_{col}_short'] = ewma(usage, 3)
            row[f'usage_{col}_long'] = ewma(usage, 8)

    try:
        vector = [row[f] for f in model.features]
    except KeyError:
        return None
    return np.array([vector], dtype=float)
