"""Post-hoc calibration of every model's P(over).

Measured on 2025-26 games the models never saw, both the ensemble and the
trained model overstated overs at the lines people actually price: at a
sportsbook-style line (a player's recent median), receiving yards cleared 42%
of the time while the models said 47-48%, and rushing yards 26% against 31-34%.
A prop tool that says 48% has to mean 48%.

The fix is a Platt map per stat and model - two numbers, a and b, applied as

    p' = sigmoid(a * logit(p) + b)

It is monotone in p, so a higher line can never come out more likely to clear
than a lower one, and it is small enough to ship in the bundle and apply
identically in the browser.

What it is fitted on matters as much as the form. A map fitted only on
sportsbook-style lines fixed those and broke the fixed alt-line ladder the line
explorer shows; one fitted only on the ladder does the reverse. So the fit uses
both, each with equal total weight: every calibration row contributes its
player-relative lines (a sportsbook-style line and the player's own 25th, 50th
and 75th percentile lines) and a fixed ladder across the stat's range.

It is fitted on the trained model's holdout season - the one season that model
never trained on - so its predictions there are honest out-of-sample ones. The
specified models don't train at all, and use the same season so the maps
describe the same league. No matchup shift is applied while fitting: it is a
small, separate adjustment, and fitting on it would tie the maps to this
week's defense windows.
"""

from __future__ import annotations

import logging

import numpy as np

from core.data_loader import cached, load_career_data
from core.projection_models import MODELS, decay_weights, run_model

logger = logging.getLogger(__name__)

# Enough rows for two parameters many times over, while keeping the build fast:
# every row is priced by five models at ~14 lines each.
CALIBRATION_ROWS = 2000
MIN_ROWS = 150
MIN_PRIOR_GAMES = 3
LADDER_QUANTILES = np.linspace(0.05, 0.95, 10)
# Keeps a map from running away on a thin sample; a=1, b=0 is "leave it alone".
L2 = 1e-3
_EPS = 1e-4
# A fit outside these is not a correction but a model whose probabilities are
# too coarse to calibrate - the triangular, bounded by the range of a player's
# games, says exactly 0% or 100% at most lines, and a map fitted to that runs
# away (a slope in the thousands) and would push everything to 0 or 1. Such a
# model gets no map: its probabilities stay raw rather than being made worse.
SLOPE_RANGE = (0.25, 4.0)
MAX_INTERCEPT = 3.0

SPECIFIED_MODELS = [key for key in MODELS if key != 'ml']


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


def _sigmoid(z):
    """1 / (1 + e^-z), written via tanh so a steep map can't overflow exp()."""
    return 0.5 * (1.0 + np.tanh(np.asarray(z, dtype=float) / 2.0))


def apply_map(p: float, ab) -> float:
    """Calibrated P(over). `ab` is (a, b); None leaves the probability alone."""
    if ab is None:
        return float(p)
    return float(_sigmoid(ab[0] * float(_logit(p)) + ab[1]))


def fit_map(p: np.ndarray, hit: np.ndarray, weight: np.ndarray) -> tuple[float, float] | None:
    """Weighted Platt fit by Newton's method.

    Rounded to the bundle's own precision (4 decimals), so Python applies
    exactly the map the browser reads - a 6-decimal map in Python against a
    4-decimal one in the bundle would already be enough to break parity."""
    x, y = _logit(p), np.asarray(hit, dtype=float)
    w = np.asarray(weight, dtype=float)
    w = w / w.mean()
    # Both parameters are gently held toward the identity map (a=1, b=0). That
    # also keeps the Hessian invertible when a model's probabilities barely
    # vary across the sample - the case that otherwise leaves the slope
    # undetermined and the solve singular.
    a, b = 1.0, 0.0
    converged = False
    for _ in range(100):
        q = _sigmoid(a * x + b)
        h = w * q * (1 - q)
        grad = np.array([np.mean(w * (q - y) * x) + L2 * (a - 1), np.mean(w * (q - y)) + L2 * b])
        hess = np.array([[np.mean(h * x * x) + L2, np.mean(h * x)], [np.mean(h * x), np.mean(h) + L2]])
        step = np.linalg.solve(hess, grad)
        a, b = a - step[0], b - step[1]
        if np.max(np.abs(step)) < 1e-10:
            converged = True
            break
    sane = np.isfinite(a) and np.isfinite(b) and SLOPE_RANGE[0] <= a <= SLOPE_RANGE[1] and abs(b) <= MAX_INTERCEPT
    if not (converged and sane):
        return None
    return round(float(a), 4), round(float(b), 4)


def _player_lines(values: np.ndarray) -> np.ndarray:
    """A sportsbook-style line and the player's own quartile lines, as x.5."""
    recent = values[-17:]
    quartiles = np.floor(np.percentile(recent, [25, 50, 75])) + 0.5
    return np.r_[np.floor(np.median(values[-8:])) + 0.5, quartiles]


def calibration_rows(stat: str, positions: list[str], season: int) -> list[dict]:
    """Player-games in `season` at `positions`, each with its prior history."""
    career = load_career_data()
    career = career.sort_values(['player_display_name', 'season', 'week'])
    rows = []
    for name, games in career.groupby('player_display_name', observed=True, sort=False):
        played = games[games[stat].notna()]
        seasons = played['season'].to_numpy(int)
        values = played[stat].to_numpy(float)
        weeks = played['week'].to_numpy(int)
        positions_played = played['position'].astype(str).to_numpy()
        for i in np.flatnonzero(seasons == season):
            if i >= MIN_PRIOR_GAMES and positions_played[i] in positions:
                rows.append({'player': str(name), 'week': int(weeks[i]), 'y': values[i],
                             'values': values[:i], 'seasons': seasons[:i]})
    rng = np.random.default_rng(7)
    if len(rows) > CALIBRATION_ROWS:
        rows = [rows[i] for i in sorted(rng.choice(len(rows), CALIBRATION_ROWS, replace=False))]
    return rows


def _ladder(rows: list[dict]) -> np.ndarray:
    outcomes = np.array([r['y'] for r in rows])
    return np.unique(np.floor(np.quantile(outcomes, LADDER_QUANTILES)) + 0.5)


def _fit_from(prob_rows: list[np.ndarray], player_lines: np.ndarray, ladder: np.ndarray,
              outcomes: np.ndarray) -> tuple[float, float] | None:
    """prob_rows[i] holds P(over) at row i's player lines, then at the ladder."""
    k = player_lines.shape[1]
    p = np.asarray(prob_rows)
    hits = np.c_[outcomes[:, None] >= player_lines, outcomes[:, None] >= ladder[None, :]]
    weight = np.c_[np.full((len(p), k), 1.0 / k), np.full((len(p), len(ladder)), 1.0 / len(ladder))]
    return fit_map(p.ravel(), hits.ravel(), weight.ravel())


def build_calibration(stat: str) -> dict[str, tuple[float, float]]:
    """{model: (a, b)} for one stat. Empty when there isn't enough to fit on."""
    from core.ml_model import POSITIONS_FOR_STAT, _DEFAULT_POSITIONS, _build_frame, get_model

    trained = get_model(stat)
    if trained is None:
        return {}
    holdout = int(trained.seasons[1])
    positions = POSITIONS_FOR_STAT.get(stat, _DEFAULT_POSITIONS)
    rows = calibration_rows(stat, positions, holdout)
    if len(rows) < MIN_ROWS:
        logger.warning("Not enough %s rows to calibrate %s (%d)", holdout, stat, len(rows))
        return {}

    ladder = _ladder(rows)
    player_lines = np.array([_player_lines(r['values']) for r in rows])
    outcomes = np.array([r['y'] for r in rows])
    maps: dict[str, tuple[float, float]] = {}

    for key in SPECIFIED_MODELS:
        probs = []
        for r, lines in zip(rows, player_lines):
            w = decay_weights(r['seasons'])
            probs.append([run_model(key, r['values'], w, float(line), stat).prob_over
                          for line in np.r_[lines, ladder]])
        _keep(maps, stat, key, _fit_from(probs, player_lines, ladder, outcomes))

    # The trained model, on the same rows, from its own features for those games.
    # Looked up by position rather than by indexing the frame on (player, week):
    # 'week' is itself one of the model's features and has to stay a column.
    frame, features = _build_frame(stat)
    frame = frame[frame['season'] == holdout]
    position_of = {
        (str(player), int(week)): i
        for i, (player, week) in enumerate(zip(frame['player_display_name'], frame['week']))
    }
    kept = [i for i, r in enumerate(rows) if (r['player'], r['week']) in position_of]
    if len(kept) >= MIN_ROWS:
        X = frame[features].to_numpy(float)[[position_of[(rows[i]['player'], rows[i]['week'])] for i in kept]]
        predictions = trained.predict(X)
        probs = [
            [trained.prob_over(float(pred), float(line)) for line in np.r_[player_lines[i], ladder]]
            for pred, i in zip(predictions, kept)
        ]
        _keep(maps, stat, 'ml', _fit_from(probs, player_lines[kept], ladder, outcomes[kept]))
    return maps


def _keep(maps: dict, stat: str, model: str, ab: tuple[float, float] | None) -> None:
    """Store a fitted map, or record that the model is left raw."""
    if ab is None:
        logger.info("    %s/%s: probabilities too coarse to calibrate; left raw", stat, model)
    else:
        maps[model] = ab


def get_calibration(stat: str) -> dict[str, tuple[float, float]]:
    """Cached maps for `stat`; they expire with the data they were fitted on."""
    try:
        return cached(f"calibration:{stat}", lambda: build_calibration(stat))
    except Exception:  # noqa: BLE001 - an unfitted map must never break a projection
        logger.exception("Calibration failed for %s; leaving probabilities raw", stat)
        return {}


def calibrate(stat: str, model: str, p: float) -> float:
    return apply_map(p, get_calibration(stat).get(model))


__all__ = ['apply_map', 'build_calibration', 'calibrate', 'fit_map', 'get_calibration']
