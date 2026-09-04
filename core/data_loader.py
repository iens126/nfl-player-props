"""Data access layer: pulls NFL data from nflverse (via nflreadpy) and
caches the resulting pandas DataFrames in memory for the life of the process.

nflreadpy already caches its own downloads for ~24h, but this module adds a
second layer that also avoids repeatedly re-running the pandas conversion /
filtering, and gives the rest of the app (and the web backend) one place to
force a refresh.
"""

import os
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


def cached(key, loader):
    """Memoize a value derived from the loaded data under the same TTL.

    Lookups built *from* these DataFrames (e.g. the depth-chart rank map) have
    to expire when the DataFrames do, or a refresh leaves them describing data
    that is no longer loaded. Routing them through this cache means
    clear_cache() drops them along with their source.
    """
    return _cached(key, loader)


def clear_cache():
    """Force the next data access to re-fetch from nflverse."""
    _cache.clear()


def load_team_data(year=None):
    return _cached(f"team_stats:{year}", lambda: nfl.load_team_stats(year).to_pandas())


def load_player_data(year=None):
    return _cached(f"player_stats:{year}", lambda: nfl.load_player_stats(year).to_pandas())


def load_pbp_data(year=None):
    """Play-by-play for a season. Large (~50k rows, 372 columns) but only ever
    loaded at build time, by the precompute, never per request."""
    return _cached(f"pbp:{year}", lambda: nfl.load_pbp(year).to_pandas())


def load_player_positions():
    """gsis_id -> position, for joining play-by-play to a player's position.

    Play-by-play identifies players by gsis_id, which is a stable key - unlike
    the abbreviated names it also carries ("J.Smith-Njigba"), which would need
    fuzzy matching.
    """
    def _load():
        rosters = nfl.load_rosters().to_pandas()
        rosters = rosters.dropna(subset=['gsis_id', 'position'])
        return dict(zip(rosters['gsis_id'], rosters['position']))
    return _cached("player_positions", _load)


def load_depth_data(year=None):
    return _cached(f"depth_charts:{year}", lambda: nfl.load_depth_charts(year).to_pandas())


# How many seasons of history to pull for career views and model training.
# Every extra season is roughly 1MB in memory once pruned, so this is cheap,
# but the further back we go the less the data resembles the current league.
CAREER_SEASONS = int(os.environ.get("CAREER_SEASONS", "8"))

_CAREER_COLUMNS = [
    'player_display_name', 'position', 'season', 'week', 'season_type',
    'team', 'opponent_team',
] + bettable_columns

_CATEGORICAL_COLUMNS = ['player_display_name', 'position', 'team', 'opponent_team', 'season_type']


def load_career_data():
    """Multi-season game logs, for career hit rates and model training.

    load_player_data() deliberately stays scoped to the current season - the
    defense rankings and matchup weights are about *this* year's teams. Career
    questions ("how often has he cleared 60 yards?") and anything we want to
    train a model on need the longer history, so they come from here instead.

    Columns are pruned and the string columns cast to categoricals, which takes
    roughly 130k rows from ~113MB down to under 10MB - worth doing on a
    512MB free-tier box.
    """
    def _load():
        current = nfl.get_current_season()
        seasons = list(range(current - CAREER_SEASONS + 1, current + 1))
        df = nfl.load_player_stats(seasons=seasons).to_pandas()
        df = df[[c for c in _CAREER_COLUMNS if c in df.columns]].copy()
        for col in _CATEGORICAL_COLUMNS:
            if col in df.columns:
                df[col] = df[col].astype('category')
        return df.sort_values(['season', 'week'])

    return _cached("career_stats", _load)


def find_player_career(name, include_postseason=True):
    """Every recorded game for `name`, oldest first, across loaded seasons."""
    df = load_career_data()
    out = df[df['player_display_name'] == name]
    if not include_postseason and 'season_type' in out.columns:
        out = out[out['season_type'] == 'REG']
    return out.sort_values(['season', 'week'])


def load_current_rosters():
    """Each active player's current team/position, from nflverse's roster data.

    Unlike load_player_data() (weekly stat lines, which only exist once a
    season's games have actually been played and otherwise still reflect
    whatever team a player last recorded a stat for), nflreadpy's
    load_rosters(seasons=None) resolves to "the current roster year" and is
    updated for trades/cuts/signings independent of games played - so it
    stays accurate through the offseason, when stats have gone stale.
    """
    def _load():
        df = nfl.load_rosters().to_pandas()
        df = df[df['status'] == 'ACT']
        # nflverse has shipped this both as a weekly table (several rows per
        # player, latest week wins) and as a flat one-row-per-player snapshot.
        # Sort by week only when it's there, so a schema change upstream
        # doesn't take the whole build down.
        if 'week' in df.columns:
            df = df.sort_values('week')
        df = df.drop_duplicates('full_name', keep='last')
        return df.set_index('full_name')[['team', 'position']]
    return _cached("current_rosters", _load)


def current_team_and_position(name: str, fallback_df: pd.DataFrame) -> tuple[str, str]:
    """A player's current (team, position), preferring the live roster and
    falling back to their most recent stat line (e.g. for a player who left
    the league, or a name that doesn't match cleanly between datasets)."""
    roster = load_current_rosters()
    if name in roster.index:
        row = roster.loc[name]
        return row['team'], row['position']
    return fallback_df['team'].iloc[-1], fallback_df['position'].iloc[-1]


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
                # Secondary color, used as a fallback when two teams in the
                # same chart have near-identical primaries.
                'color2': row.get('team_color2'),
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
