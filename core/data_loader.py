"""Data access layer: pulls NFL data from nflverse (via nflreadpy) and
caches the resulting pandas DataFrames in memory for the life of the process.

nflreadpy already caches its own downloads for ~24h, but this module adds a
second layer that also avoids repeatedly re-running the pandas conversion /
filtering, and gives the rest of the app (and the web backend) one place to
force a refresh.
"""

import time

import nflreadpy as nfl
import pandas as pd
from datetime import datetime, timedelta

bettable_columns = [
    'passing_yards', 'passing_tds', 'completions', 'attempts', 'passing_interceptions',
    'targets', 'receptions', 'receiving_yards', 'receiving_tds',
    'carries', 'rushing_yards', 'rushing_tds',
]

# How long to trust an in-memory dataset before re-fetching from nflverse.
_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_cache: dict[str, tuple[float, object]] = {}


def _cached(key, loader):
    entry = _cache.get(key)
    now = time.time()
    if entry is not None and (now - entry[0]) < _CACHE_TTL_SECONDS:
        return entry[1]
    value = loader()
    _cache[key] = (now, value)
    return value


def clear_cache():
    """Force the next data access to re-fetch from nflverse."""
    _cache.clear()


def load_team_data(year=None):
    return _cached(f"team_stats:{year}", lambda: nfl.load_team_stats(year).to_pandas())


def load_player_data(year=None):
    return _cached(f"player_stats:{year}", lambda: nfl.load_player_stats(year).to_pandas())


def load_depth_data(year=None):
    return _cached(f"depth_charts:{year}", lambda: nfl.load_depth_charts(year).to_pandas())


def load_team_meta():
    """Reference metadata (full team name, primary color) - not season stats.
    Colors are used for lightweight UI accents only; team logos/wordmarks from
    this dataset are intentionally not surfaced (see README on NFL branding)."""
    def _load():
        df = nfl.load_teams().to_pandas()
        meta = {}
        for _, row in df.iterrows():
            meta[row['team_abbr']] = {
                'full': row['team_name'],
                'nickname': row.get('team_nick'),
                'color': row.get('team_color'),
            }
        return meta
    return _cached("team_meta", _load)


def upcoming_schedule(days=7):
    current_season = nfl.get_current_season()
    schedule = _cached(
        f"schedule:{current_season}",
        lambda: nfl.load_schedules([current_season, current_season + 1]).to_pandas(),
    )
    schedule = schedule.copy()
    schedule['gameday'] = pd.to_datetime(schedule['gameday']).dt.date
    today = datetime.today().date()
    end_date = today + timedelta(days=days)
    upcoming = schedule[
        (schedule['gameday'] >= today) &
        (schedule['gameday'] <= end_date)
    ].sort_values("gameday")
    return upcoming


def get_pos(team, pos):
    player_stats = load_player_data()
    names = player_stats[
        (player_stats['team'] == team.upper()) & (player_stats['position'] == pos.upper())
    ]['player_display_name'].unique()
    return list(names)


def find_player(name):
    player_stats = load_player_data()
    df = player_stats[player_stats['player_display_name'] == name]
    if df.empty:
        return df
    df = df.drop(columns=['player_id', 'player_name', 'position_group', 'season'])
    keep_cols = ['player_display_name'] + ['headshot_url'] + ['week'] + ['position'] + ['team'] + ['opponent_team'] + bettable_columns
    df = df[keep_cols]
    df = df.dropna(how='all', axis=1)
    df = df.loc[:, (df != 0).any(axis=0)]
    df = df.sort_values('week', ascending=True)
    return df


def pass_def(team):
    team_stats = load_team_data()
    passing_stats = ['week', 'team', 'opponent_team', 'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions']
    def_df = team_stats[passing_stats].copy()
    def_df['Team'] = def_df['opponent_team']
    def_df = def_df.drop(columns='opponent_team')
    def_df['Opponent'] = def_df['team']
    def_df = def_df.drop(columns='team')
    def_df['yards_per_att'] = def_df['passing_yards'] / def_df['attempts']
    def_df['passing_points'] = def_df['passing_tds'] * 6
    def_df = def_df[def_df['Team'] == team.upper()]
    return def_df


def run_def(team):
    team_stats = load_team_data()
    rushing_stats = ['week', 'team', 'opponent_team', 'carries', 'rushing_yards', 'rushing_tds']
    def_df = team_stats[rushing_stats].copy()
    def_df['Team'] = def_df['opponent_team']
    def_df = def_df.drop(columns='opponent_team')
    def_df['Opponent'] = def_df['team']
    def_df = def_df.drop(columns='team')
    def_df['yards_per_car'] = def_df['rushing_yards'] / def_df['carries']
    def_df['rushing_points'] = def_df['rushing_tds'] * 6
    def_df = def_df[def_df['Team'] == team.upper()]
    return def_df
