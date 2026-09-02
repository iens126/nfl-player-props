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

from core.data_loader import (
    load_team_data, load_player_data, load_depth_data,
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


def best_name_match(name, name_list, threshold=85):
    if len(name_list) == 0:
        return None
    match, score, _ = process.extractOne(name, name_list, scorer=fuzz.token_sort_ratio)
    if score >= threshold:
        return match
    return None


_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}


def _normalize_name(name):
    """Casefold and strip punctuation/suffixes so 'A.J. Brown' == 'AJ Brown'."""
    cleaned = ''.join(c for c in str(name).lower() if c.isalnum() or c.isspace())
    parts = [p for p in cleaned.split() if p not in _SUFFIXES]
    return ' '.join(parts)


def pos_rank_map():
    """Every player's depth-chart rank, resolved in one pass.

    This used to be a per-player lookup: for each of the ~140 players in a
    position group it re-scanned the full stats and depth-chart frames and ran
    a fuzzy match, which cost over a second on the first projection. Names
    agree exactly far more often than not, so match the whole league at once on
    a normalized key and fall back to fuzzy matching only for the leftovers.

    Cached with the data it is derived from, so a refresh rebuilds it rather
    than leaving ranks that describe an older depth chart.
    """
    def _build():
        depth = load_depth_data()
        player_stats = load_player_data()

        depth = depth[['player_name', 'pos_abb', 'pos_rank']].dropna(subset=['player_name', 'pos_abb'])
        depth = depth.drop_duplicates(subset=['player_name', 'pos_abb'], keep='first')
        depth = depth.assign(norm_key=depth['player_name'].map(_normalize_name))

        # (position, normalized name) -> rank, plus the candidate pool per
        # position for the fuzzy fallback.
        exact = {(row.pos_abb, row.norm_key): row.pos_rank for row in depth.itertuples()}
        by_position = depth.groupby('pos_abb')['norm_key'].unique().to_dict()

        players = player_stats[['player_display_name', 'position']].dropna().drop_duplicates(
            subset=['player_display_name'], keep='last')

        ranks = {}
        for name, pos in players.itertuples(index=False):
            key = _normalize_name(name)
            rank = exact.get((pos, key))
            if rank is None:
                match = best_name_match(key, by_position.get(pos, []))
                rank = exact.get((pos, match)) if match is not None else None
            ranks[name] = np.nan if rank is None else rank
        return ranks

    return cached("pos_rank_map", _build)


def get_pos_rank(name):
    """A player's depth-chart rank at their position (1 = starter)."""
    return pos_rank_map().get(name, np.nan)


def by_positon_rank(defense, pos, stat_cat):
    """Average/std of `stat_cat` grouped by depth-chart rank (1/2/3/other) for a
    position, either league-wide (defense='NFL') or against one specific defense."""
    def _build():
        player_stats = load_player_data()
        if defense == 'NFL':
            positional_stats = player_stats[player_stats['position'] == pos].copy()
        else:
            positional_stats = player_stats[(player_stats['opponent_team'] == defense) & (player_stats['position'] == pos)].copy()

        positional_stats['rank'] = positional_stats['player_display_name'].map(pos_rank_map())

        positional_stats['rank_group'] = positional_stats['rank'].apply(
            lambda r: r if r in [1, 2, 3] else 'other'
        )

        stats = (positional_stats.groupby('rank_group')[stat_cat].agg(['mean', 'std', 'count']).reset_index())

        for group in [1, 2, 3, 'other']:
            if group not in stats['rank_group'].values:
                stats.loc[len(stats)] = [group, np.nan, np.nan, 0]

        return stats

    return cached(f"pos_rank_stats:{defense}:{pos}:{stat_cat}", _build)


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
