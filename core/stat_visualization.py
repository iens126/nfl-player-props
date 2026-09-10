"""Player-vs-defense weekly comparison series, used to drive the performance chart.

This preserves the original analytics (which stat maps to which defensive
category, and how player/defense weeks get aligned) but returns plain data
instead of a rendered matplotlib figure, since the web frontend renders its
own interactive chart from JSON.
"""

import pandas as pd

from core.data_loader import find_player_career, load_career_data, pass_def, run_def
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
    """The player's games, one by one, against what `defense` allowed.

    `last_n` takes the player's last N games wherever they fell - the same
    rolling list the projection reads. No `last_n` means their most recent
    season, which for someone who hasn't played yet this year is last year.
    Each game is paired with what this defense allowed in the same season and
    week, when that week falls inside the defense's own rolling window.
    """
    if stat_cat not in STAT_MAP:
        raise ValueError(f"Unsupported stat category '{stat_cat}'")

    games = find_player_career(player)
    if games.empty or stat_cat not in games.columns:
        raise ValueError(f"'{stat_cat}' has no recorded data for {player}")
    if last_n:
        games = games.tail(last_n)
    else:
        games = games[games['season'] == games['season'].max()]

    def_stat, def_type = STAT_MAP[stat_cat]
    def_df = pass_def(defense) if def_type == 'pass' else run_def(defense)
    allowed = {
        (int(season), int(week)): value
        for season, week, value in zip(def_df['season'], def_df['week'], def_df[def_stat])
    }
    # Weeks repeat across a season boundary, so label with the season then.
    spans_seasons = games['season'].nunique() > 1

    records = []
    for _, row in games.iterrows():
        season, week = int(row['season']), int(row['week'])
        value = row[stat_cat]
        defense_value = allowed.get((season, week))
        records.append({
            'week': week,
            'season': season if spans_seasons else None,
            'label': f"'{str(season)[2:]} W{week}" if spans_seasons else f"W{week}",
            'opponent': None if pd.isna(row['opponent_team']) else str(row['opponent_team']),
            'player_value': None if pd.isna(value) else float(value),
            'defense_allowed': None if defense_value is None or pd.isna(defense_value) else float(defense_value),
        })

    player_values = [r['player_value'] for r in records if r['player_value'] is not None]
    defense_values = [r['defense_allowed'] for r in records if r['defense_allowed'] is not None]

    return {
        'stat': stat_cat,
        'defense_stat': def_stat,
        'defense_team': defense,
        'weeks': records,
        'player_average': sum(player_values) / len(player_values) if player_values else None,
        'defense_average': sum(defense_values) / len(defense_values) if defense_values else None,
    }
