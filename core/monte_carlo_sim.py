"""Matchup-adjusted Monte Carlo projection engine.

Methodology (used verbatim by the API / frontend "how is this calculated" copy):
  1. Take the player's last `window` (3) games for the selected stat and fit a
     triangular distribution using the min, mean, and max of that window.
  2. Draw `n_simulations` (10,000) samples from that distribution.
  3. Compute a matchup weight that shifts the distribution up or down based on
     how the selected opponent defends that stat relative to the league:
       - QB stats: weight = k * player_std * -zdef, where zdef is the
         opponent's z-score (vs league mean/std) for the equivalent team stat.
       - RB/WR/TE stats: weight = k * (defense_avg - league_avg), where both
         averages are computed for players at the same depth-chart rank as
         the player being projected (e.g. WR1 vs WR1), since a defense's
         production allowed to a "WR1" is a better proxy for a matchup than
         its blended average across every receiver it has faced.
  4. Add the weight to every simulated draw. The mean of the adjusted
     simulations is the model's point projection; the share of simulations
     at/above the requested line is the over probability (1 - that = under).
"""

import numpy as np
import pandas as pd
from rapidfuzz import process, fuzz
from functools import lru_cache

from core.data_loader import (
    load_team_data, load_player_data, load_depth_data,
    find_player, pass_def, run_def,
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


def best_name_match(name, name_list, threshold=85):
    if len(name_list) == 0:
        return None
    match, score, _ = process.extractOne(name, name_list, scorer=fuzz.token_sort_ratio)
    if score >= threshold:
        return match
    return None


# Cached because by_positon_rank() calls this once per unique player in a position
# group (100+ players league-wide) and the result is deterministic for the life of
# the loaded data (cleared automatically whenever data_loader's cache is cleared).
@lru_cache(maxsize=None)
def get_pos_rank(name):
    """A player's depth-chart rank at their position (1 = starter), via fuzzy name match."""
    depth = load_depth_data()
    player_stats = load_player_data()
    positions = player_stats[player_stats['player_display_name'] == name]['position'].unique()
    if len(positions) == 0:
        return np.nan
    pos = positions[0]
    depth_names = depth[depth['pos_abb'] == pos]['player_name'].unique()
    match = best_name_match(name, depth_names)

    if match is None:
        return np.nan

    rank = depth[(depth['player_name'] == match) & (depth['pos_abb'] == pos)]['pos_rank'].iloc[0]
    return rank


def by_positon_rank(defense, pos, stat_cat):
    """Average/std of `stat_cat` grouped by depth-chart rank (1/2/3/other) for a
    position, either league-wide (defense='NFL') or against one specific defense."""
    player_stats = load_player_data()
    if defense == 'NFL':
        positional_stats = player_stats[player_stats['position'] == pos].copy()
    else:
        positional_stats = player_stats[(player_stats['opponent_team'] == defense) & (player_stats['position'] == pos)].copy()

    positional_stats['rank'] = positional_stats['player_display_name'].map(
        {p: get_pos_rank(p) for p in positional_stats['player_display_name'].unique()})

    positional_stats['rank_group'] = positional_stats['rank'].apply(
        lambda r: r if r in [1, 2, 3] else 'other'
    )

    stats = (positional_stats.groupby('rank_group')[stat_cat].agg(['mean', 'std', 'count']).reset_index())

    for group in [1, 2, 3, 'other']:
        if group not in stats['rank_group'].values:
            stats.loc[len(stats)] = [group, np.nan, np.nan, 0]

    return stats


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
        k = POSITION_K.get(pos, DEFAULT_K)
        player_std = find_player(name)[stat_cat].std()
        rank = get_pos_rank(name)
        rank_idx = {1: 0, 2: 1, 3: 2}.get(rank, 3)

        league_avg = by_positon_rank('NFL', pos, stat_cat).iat[rank_idx, 1]
        defense_avg = by_positon_rank(def_team, pos, stat_cat).iat[rank_idx, 1]

        weight = k * (defense_avg - league_avg)

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
