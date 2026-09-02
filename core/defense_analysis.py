"""League-wide defensive aggregates and rankings, built from the same
team_stats data source as pass_def()/run_def() in data_loader.py.

Rankings are computed strictly from the currently loaded dataset (one
season of team_stats) - nothing here is hardcoded or invented.
"""

import pandas as pd

from core.data_loader import load_team_data, pass_def, run_def

# For each stat, whether a *lower* value allowed is better defense (True) or
# a *higher* value is better (e.g. more interceptions forced is good defense).
LOWER_IS_BETTER = {
    'completions': True,
    'attempts': True,
    'passing_yards': True,
    'passing_tds': True,
    'passing_interceptions': False,
    'yards_per_att': True,
    'carries': True,
    'rushing_yards': True,
    'rushing_tds': True,
    'yards_per_car': True,
}

RECENT_WINDOW = 3


def _league_pass_defense():
    team_stats = load_team_data()
    agg = team_stats.groupby('opponent_team').agg(
        completions=('completions', 'mean'),
        attempts=('attempts', 'mean'),
        passing_yards=('passing_yards', 'mean'),
        passing_tds=('passing_tds', 'mean'),
        passing_interceptions=('passing_interceptions', 'mean'),
    ).reset_index().rename(columns={'opponent_team': 'team'})
    agg['yards_per_att'] = agg['passing_yards'] / agg['attempts']
    return agg


def _league_run_defense():
    team_stats = load_team_data()
    agg = team_stats.groupby('opponent_team').agg(
        carries=('carries', 'mean'),
        rushing_yards=('rushing_yards', 'mean'),
        rushing_tds=('rushing_tds', 'mean'),
    ).reset_index().rename(columns={'opponent_team': 'team'})
    agg['yards_per_car'] = agg['rushing_yards'] / agg['carries']
    return agg


def _ranks_for_team(league_df, team, cols):
    ranks = {}
    n_teams = len(league_df)
    for col in cols:
        ascending = LOWER_IS_BETTER.get(col, True)
        ranked = league_df[['team', col]].dropna().sort_values(col, ascending=ascending).reset_index(drop=True)
        match = ranked.index[ranked['team'] == team]
        if len(match) == 0:
            continue
        ranks[col] = {
            'rank': int(match[0]) + 1,
            'of': n_teams,
            'value': float(ranked.loc[match[0], col]),
        }
    return ranks


def _weekly_records(df, cols):
    records = []
    for _, row in df.sort_values('week').iterrows():
        rec = {'week': int(row['week']), 'opponent': row['Opponent']}
        for c in cols:
            rec[c] = None if pd.isna(row[c]) else float(row[c])
        records.append(rec)
    return records


def defense_summary(team):
    """Full defensive picture for one team: weekly logs, season/recent
    averages, and league rank for both pass and rush defense."""
    team = team.upper()

    pdf = pass_def(team)
    rdf = run_def(team)

    pass_cols = ['completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions', 'yards_per_att']
    rush_cols = ['carries', 'rushing_yards', 'rushing_tds', 'yards_per_car']

    pass_recent = pdf.sort_values('week').tail(RECENT_WINDOW)
    rush_recent = rdf.sort_values('week').tail(RECENT_WINDOW)

    league_pass = _league_pass_defense()
    league_run = _league_run_defense()

    return {
        'team': team,
        'passing': {
            'weekly': _weekly_records(pdf, pass_cols),
            'season_average': {c: _safe_mean(pdf[c]) for c in pass_cols},
            'recent_average': {c: _safe_mean(pass_recent[c]) for c in pass_cols},
            'league_rank': _ranks_for_team(league_pass, team, pass_cols),
            'league_size': len(league_pass),
        },
        'rushing': {
            'weekly': _weekly_records(rdf, rush_cols),
            'season_average': {c: _safe_mean(rdf[c]) for c in rush_cols},
            'recent_average': {c: _safe_mean(rush_recent[c]) for c in rush_cols},
            'league_rank': _ranks_for_team(league_run, team, rush_cols),
            'league_size': len(league_run),
        },
    }


def _safe_mean(series):
    val = series.mean()
    return None if pd.isna(val) else float(val)
