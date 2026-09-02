"""Player-vs-defense weekly comparison series, used to drive the performance chart.

This preserves the original analytics (which stat maps to which defensive
category, and how player/defense weeks get aligned) but returns plain data
instead of a rendered matplotlib figure, since the web frontend renders its
own interactive chart from JSON.
"""

import pandas as pd

from core.data_loader import find_player, find_player_career, load_career_data, pass_def, run_def
from core.monte_carlo_sim import STAT_MAP


def career_series(player, stat_cat, defense):
    """The player's whole career, game by game, against the same defense reference.

    Weeks repeat across seasons, so career rows are labelled "'23 W5" and carry
    an explicit season. A single past game can't be aligned to what this
    defense allowed that same week, so the comparison bar here is what the
    defense allowed to the player's position across that season - still a fair
    like-for-like, just at season resolution rather than weekly.
    """
    if stat_cat not in STAT_MAP:
        raise ValueError(f"Unsupported stat category '{stat_cat}'")

    games = find_player_career(player)
    if games.empty or stat_cat not in games.columns:
        raise ValueError(f"'{stat_cat}' has no recorded data for {player}")

    position = str(games['position'].iloc[-1])
    career = load_career_data()
    allowed = career[
        (career['opponent_team'].astype(str) == defense) & (career['position'].astype(str) == position)
    ]
    by_season = allowed.groupby('season', observed=True)[stat_cat].mean().to_dict()

    records = []
    for _, row in games.iterrows():
        season = int(row['season'])
        value = row[stat_cat]
        defense_value = by_season.get(season)
        records.append({
            'week': int(row['week']),
            'season': season,
            'label': f"'{str(season)[2:]} W{int(row['week'])}",
            'opponent': None if pd.isna(row['opponent_team']) else str(row['opponent_team']),
            'player_value': None if pd.isna(value) else float(value),
            'defense_allowed': None if defense_value is None or pd.isna(defense_value) else float(defense_value),
        })

    player_values = games[stat_cat].dropna()
    return {
        'stat': stat_cat,
        'defense_stat': STAT_MAP[stat_cat][0],
        'defense_team': defense,
        'weeks': records,
        'player_average': float(player_values.mean()) if len(player_values) else None,
        'defense_average': float(allowed[stat_cat].mean()) if len(allowed) else None,
    }


def comparison_series(player, stat_cat, defense, last_n=None):
    """Weekly player performance vs. what `defense` allows at the equivalent stat.

    Returns a dict with a `weeks` list of {week, opponent, player_value, defense_allowed}
    plus player/defense season averages. `last_n` optionally restricts to the
    player's most recent N games (by week number) before defense weeks are aligned.
    """
    if stat_cat not in STAT_MAP:
        raise ValueError(f"Unsupported stat category '{stat_cat}'")

    stats_df = find_player(player).sort_values("week")
    if last_n:
        stats_df = stats_df.tail(last_n)

    if stat_cat not in stats_df.columns:
        raise ValueError(f"'{stat_cat}' has no recorded data for {player}")

    def_stat, def_type = STAT_MAP[stat_cat]
    def_df = pass_def(defense) if def_type == 'pass' else run_def(defense)

    weeks = sorted(set(stats_df['week']).union(set(def_df['week'])))
    combined = pd.DataFrame({'week': weeks}).set_index('week')
    combined['player'] = stats_df.set_index('week')[stat_cat]
    combined['opponent'] = stats_df.set_index('week')['opponent_team'] if 'opponent_team' in stats_df.columns else None
    combined['defense'] = def_df.set_index('week')[def_stat]

    if last_n:
        combined = combined[combined.index.isin(stats_df['week'])]

    records = []
    for week, row in combined.iterrows():
        records.append({
            'week': int(week),
            'season': None,
            'label': f"W{int(week)}",
            'opponent': None if pd.isna(row['opponent']) else row['opponent'],
            'player_value': None if pd.isna(row['player']) else float(row['player']),
            'defense_allowed': None if pd.isna(row['defense']) else float(row['defense']),
        })

    player_avg = combined['player'].mean(skipna=True)
    defense_avg = combined['defense'].mean(skipna=True)

    return {
        'stat': stat_cat,
        'defense_stat': def_stat,
        'defense_team': defense,
        'weeks': records,
        'player_average': None if pd.isna(player_avg) else float(player_avg),
        'defense_average': None if pd.isna(defense_avg) else float(defense_avg),
    }
