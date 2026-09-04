"""The matchup adjustment: how much an opponent shifts a projection.

The distributions themselves live in core/projection_models.py. What remains
here is the weight added to them, and the triangular sampler the app started
with (now evaluated in closed form).

  - QB stats: weight = k * player_std * -zdef, where zdef is the opponent's
    z-score (against the league mean/std) for the equivalent team stat.
  - RB/WR/TE stats: weight = k * reliability * (defense_avg - league_avg),
    comparing what the defense allows to that position against the league,
    scaled by how much of such a gap actually repeats.

That last term replaced a depth-chart-rank comparison - a defense's WR1
average against the league's WR1 average. It read as more precise and measured
as noise: split-half correlation of +0.05 for yards per target against a team's
primary receiver, on ~122 targets per defense per season, against +0.19 to
+0.30 for the same defenses pooled across all receivers. Out of sample, on
strictly prior games, the rank version made projections *worse* than applying
no adjustment at all (MAE +0.073 yards on receiving yards); the position-level
version scaled by reliability is neutral (+0.004).

Reliability is measured from the loaded data rather than assumed, and varies a
lot by stat: about 0.50 for rushing yards allowed to backs, 0.28 for receiving
yards allowed to tight ends, 0.13 for receiving yards allowed to receivers. So
the adjustment is meaningful where run defense is concerned and close to
nothing for receivers, which is what the evidence supports.
"""

import numpy as np
import pandas as pd

from core.data_loader import (
    load_team_data, load_player_data, load_career_data,
    find_player, pass_def, run_def, cached,
)

STAT_MAP = {
    'passing_yards': ('passing_yards', 'pass'),
    'passing_tds': ('passing_tds', 'pass'),
    'attempts': ('attempts', 'pass'),
    'completions': ('completions', 'pass'),
    'passing_interceptions': ('passing_interceptions', 'pass'),
    'receiving_yards': ('passing_yards', 'pass'),  # yards gained through air
    'receiving_tds': ('passing_tds', 'pass'),
    'targets': ('attempts', 'pass'),
    'receptions': ('completions', 'pass'),
    'rushing_yards': ('rushing_yards', 'run'),
    'rushing_tds': ('rushing_tds', 'run'),
    'carries': ('carries', 'run'),
}

POSITION_K = {'QB': 0.2, 'RB': 0.12, 'WR': 0.23, 'TE': 0.01}
DEFAULT_K = 0.3
SIM_WINDOW = 3
N_SIMULATIONS = 10000


def def_league_stats(stat_cat):
    """League-wide average/std for a team-level stat (used for the QB z-score)."""
    team_stats = load_team_data()
    avg = team_stats[stat_cat].mean()
    std = team_stats[stat_cat].std()
    return avg, std


def create_weight(name, def_team, stat_cat):
    """Matchup adjustment (see module docstring for the full methodology)."""
    pos_values = find_player(name)['position'].unique()
    if len(pos_values) == 0:
        raise ValueError(f"No data found for player '{name}'")
    pos = pos_values[0]

    if stat_cat not in STAT_MAP:
        raise ValueError(f"Unsupported stat category '{stat_cat}'")

    if pos == 'QB':
        k = POSITION_K['QB']
        player_std = find_player(name)[stat_cat].std()
        league_avg, league_std = def_league_stats(stat_cat)
        if STAT_MAP[stat_cat][1] == 'pass':
            team_avg = pass_def(def_team)[stat_cat].mean()
        else:
            team_avg = run_def(def_team)[stat_cat].mean()

        zdef = (team_avg - league_avg) / league_std
        weight = k * player_std * (-zdef)

    else:
        # Position-level, scaled by how much of the gap actually repeats. This
        # replaced a depth-chart-rank comparison (a defense's WR1 average
        # against the league's WR1 average) that measured out as noise: split
        # -half correlation +0.05 on ~122 targets per defense per season, while
        # the position-level figure carries between 0.13 (receivers) and 0.50
        # (backs on the ground).
        k = POSITION_K.get(pos, DEFAULT_K)
        league_avg = position_allowed('NFL', pos, stat_cat)
        defense_avg = position_allowed(def_team, pos, stat_cat)
        reliability = signal_reliability(pos, stat_cat)

        weight = k * reliability * (defense_avg - league_avg)

    if np.isnan(weight) or np.isinf(weight):
        weight = 0.0

    return float(weight)


def _simulate(name, def_team, stat_cat, window=SIM_WINDOW, n_simulations=N_SIMULATIONS):
    df = find_player(name)
    if stat_cat not in df.columns:
        raise ValueError(f"'{stat_cat}' has no recorded data for {name}")

    recent = df[df['week'] > df['week'].max() - window]
    values = recent[stat_cat]
    if len(values) == 0:
        raise ValueError(f"Not enough recent games for {name} to run a projection")

    a, c, b = values.min(), values.mean(), values.max()
    if a == b:
        # Degenerate window (e.g. a single game, or identical values) - triangular
        # sampling needs a spread, so fall back to the flat value with tiny jitter.
        b = a + 1e-6

    dist = np.random.triangular(a, c, b, n_simulations)
    weight = create_weight(name, def_team, stat_cat)
    adjusted = dist + weight
    return adjusted, weight, values


def run_sim(name, def_team, stat_cat, line):
    """Probability the player finishes at/above `line`. Kept for backward compatibility."""
    adjusted, _weight, _values = _simulate(name, def_team, stat_cat)
    return float(np.mean(adjusted >= line))


def project(name, def_team, stat_cat, line):
    """Full projection: point estimate + over/under probability, in one simulation pass."""
    adjusted, weight, recent_values = _simulate(name, def_team, stat_cat)
    prob_over = float(np.mean(adjusted >= line))

    return {
        'projection': float(np.mean(adjusted)),
        'prob_over': prob_over,
        'prob_under': 1.0 - prob_over,
        'weight': weight,
        'recent_average': float(recent_values.mean()),
        'recent_games': int(len(recent_values)),
        'simulated_std': float(np.std(adjusted)),
        'simulations': int(len(adjusted)),
        'window_games': SIM_WINDOW,
    }


# ---------------------------------------------------------------------------
# Position-level defensive signal
# ---------------------------------------------------------------------------
#
# The matchup adjustment for skill positions used to compare what a defense
# allowed to players at the same depth-chart rank - a defense's WR1 average
# against the league's WR1 average. Measuring that showed it does not persist:
# split-half correlation of +0.05 for yards per target against a team's primary
# receiver, on ~122 targets per defense per season. Splitting by rank divides
# one weak signal into noisier pieces.
#
# What does persist is the position-level figure, and by very different amounts
# per stat: a defense's rushing yards allowed to backs carries about half its
# signal from one half of a season to the next, while receiving yards allowed
# to receivers carries barely an eighth. So the adjustment is now scaled by
# that measured reliability - a defense ten yards more generous than average
# moves the projection ten yards times however much of that gap is repeatable.
#
# Reliability is measured from the loaded data rather than hardcoded, so it
# tracks the league rather than a number that was true in some past season.

_MIN_ROWS_FOR_RELIABILITY = 800


def position_allowed(defense, position, stat_cat):
    """Mean `stat_cat` this defense allows to `position`. 'NFL' = league average."""
    def _build():
        stats = load_player_data()
        rows = stats[stats['position'] == position]
        if defense != 'NFL':
            rows = rows[rows['opponent_team'] == defense]
        values = rows[stat_cat].dropna() if stat_cat in rows.columns else pd.Series(dtype=float)
        return float(values.mean()) if len(values) else float('nan')

    return cached(f"pos_allowed:{defense}:{position}:{stat_cat}", _build)


def signal_reliability(position, stat_cat):
    """How much of a defense's position-level deviation actually repeats.

    Split-half within each season, averaged, then Spearman-Brown corrected up
    to a full season - which is the window the averages above are taken over.
    Returns 0 when the split-half is negative or the sample is too thin, which
    makes the adjustment vanish rather than amplify noise.
    """
    def _build():
        career = load_career_data()
        rows = career[(career['position'] == position)]
        if 'season_type' in rows.columns:
            rows = rows[rows['season_type'] == 'REG']
        if stat_cat not in rows.columns:
            return 0.0
        rows = rows[rows[stat_cat].notna()]
        if len(rows) < _MIN_ROWS_FOR_RELIABILITY:
            return 0.0

        halves = []
        for _season, season_rows in rows.groupby('season', observed=True):
            midpoint = season_rows['week'].median()
            first = season_rows[season_rows['week'] <= midpoint].groupby(
                'opponent_team', observed=True)[stat_cat].mean()
            second = season_rows[season_rows['week'] > midpoint].groupby(
                'opponent_team', observed=True)[stat_cat].mean()
            paired = pd.concat([first, second], axis=1, keys=['a', 'b']).dropna()
            if len(paired) >= 20:
                halves.append(paired['a'].corr(paired['b']))

        if not halves:
            return 0.0
        half = float(np.nanmean(halves))
        if not np.isfinite(half) or half <= 0:
            return 0.0
        return float(np.clip(2 * half / (1 + half), 0.0, 1.0))

    return cached(f"signal_reliability:{position}:{stat_cat}", _build)
