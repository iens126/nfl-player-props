"""What a defense actually allowed, broken down by the role a player fills.

This answers "how does this defense do against a team's number one receiver?"
from play-by-play, counting every target rather than aggregating a game into a
single number.

It is deliberately **descriptive only**, and that is a finding rather than a
preference. Split-half correlations across 2023-25, at ~122 targets per defense
per season against a team's WR1:

    group   yds/target   completion%   EPA
    WR1        +0.049       +0.088    +0.009
    WR2        -0.090       -0.029    +0.010
    TE1        -0.057       -0.202    -0.089
    RB1        -0.033       +0.196    -0.095
    ALL        +0.188       +0.304    +0.296   <- pooled, and real

The same test on the same data finds the effects it should (offensive pass EPA
+0.56, overall defensive pass EPA allowed +0.22), so the machinery works. The
effect is simply absent: splitting a defense's season by receiver role
subdivides one weak signal into noisier pieces rather than revealing a hidden
one. Nine times more data than the game-level version changed nothing, so the
constraint was never sample size.

So these numbers say what happened. They do not forecast, and the UI says so.
The one cut that does carry information is a defense's overall pass defence,
which the existing defense summary already reports.

Roles come from usage - each receiver ranked within their own offense by target
share - not from published depth charts. Depth charts are unreliable for
receivers, and their schema changed between the 2024 and 2025 seasons; usage is
also what "WR1" is generally taken to mean.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.data_loader import cached, load_pbp_data, load_player_positions

logger = logging.getLogger(__name__)

# Only roles with enough volume to be worth reporting; deeper than third in a
# rotation the target counts get too thin to describe anything.
REPORTED_ROLES = (1, 2, 3)
POSITIONS = ('WR', 'TE', 'RB')

# A receiver needs this many targets in a season before their usage rank means
# anything - otherwise a backup with two targets in a blowout ranks as a WR3.
MIN_SEASON_TARGETS = 10


def _targeted_plays(season: int | None = None) -> pd.DataFrame:
    """Regular-season targeted passes, tagged with position and usage role."""
    pbp = load_pbp_data(season)
    # Between the end of one season and the first snap of the next, this comes
    # back empty - and an empty frame has no columns, so the filter below would
    # raise rather than simply finding nothing.
    required = {'pass_attempt', 'receiver_player_id', 'season_type'}
    if pbp.empty or not required.issubset(pbp.columns):
        return pd.DataFrame()

    plays = pbp[
        (pbp['pass_attempt'] == 1)
        & pbp['receiver_player_id'].notna()
        & (pbp['season_type'] == 'REG')
    ].copy()
    if plays.empty:
        return plays

    plays['season'] = plays['season'].astype(int)
    plays['week'] = plays['week'].astype(int)

    positions = load_player_positions()
    plays['position'] = plays['receiver_player_id'].map(positions)
    plays = plays[plays['position'].isin(POSITIONS)]

    # Usage role: rank each receiver within their own offense *and position* by
    # target volume, so WR1 is a team's most-targeted receiver and TE1 its
    # most-targeted tight end. Ranking across all pass-catchers together would
    # mean a team whose leading target is a tight end has no WR1 at all, which
    # both loses games and changes what the label means.
    targets = (
        plays.groupby(['season', 'posteam', 'position', 'receiver_player_id'], observed=True)
        .size().rename('season_targets').reset_index()
    )
    targets['role'] = (
        targets.groupby(['season', 'posteam', 'position'], observed=True)['season_targets']
        .rank(method='first', ascending=False)
    )
    plays = plays.merge(
        targets, on=['season', 'posteam', 'position', 'receiver_player_id'], how='left',
    )
    plays = plays[plays['season_targets'] >= MIN_SEASON_TARGETS]
    return plays


def defense_role_table(season: int | None = None) -> pd.DataFrame:
    """One row per defense, position and role, with what that defense allowed."""
    plays = _targeted_plays(season)
    if plays.empty:
        return pd.DataFrame()

    plays = plays[plays['role'].isin(REPORTED_ROLES)].copy()
    plays['completion'] = plays['complete_pass'].fillna(0.0)
    plays['yards'] = plays['yards_gained'].fillna(0.0)

    grouped = plays.groupby(['defteam', 'position', 'role'], observed=True)
    table = grouped.agg(
        targets=('yards', 'size'),
        receptions=('completion', 'sum'),
        yards=('yards', 'sum'),
        games=('game_id', 'nunique'),
    ).reset_index()

    table['yards_per_game'] = table['yards'] / table['games'].replace(0, np.nan)
    table['yards_per_target'] = table['yards'] / table['targets'].replace(0, np.nan)
    table['completion_rate'] = table['receptions'] / table['targets'].replace(0, np.nan)

    # League context: the average across defenses for the same position/role,
    # and where this defense sits. Rank 1 = fewest yards allowed per game.
    for column in ('yards_per_game', 'yards_per_target', 'completion_rate'):
        by_group = table.groupby(['position', 'role'], observed=True)[column]
        table[f'league_{column}'] = by_group.transform('mean')
    table['rank'] = (
        table.groupby(['position', 'role'], observed=True)['yards_per_game']
        .rank(method='min', ascending=True).astype('Int64')
    )
    table['of'] = table.groupby(['position', 'role'], observed=True)['yards_per_game'].transform('size')

    return table


def defense_roles(team: str, season: int | None = None) -> list[dict]:
    """The role breakdown for one defense, ready to serialise."""
    table = _role_table_cached(season)
    if table.empty:
        return []

    rows = table[table['defteam'] == team.upper()]
    out = []
    for row in rows.sort_values(['position', 'role']).itertuples(index=False):
        out.append({
            'position': row.position,
            'role': int(row.role),
            'label': f'{row.position}{int(row.role)}',
            'games': int(row.games),
            'targets': int(row.targets),
            'receptions': int(row.receptions),
            'yards': float(row.yards),
            'yards_per_game': _round(row.yards_per_game),
            'yards_per_target': _round(row.yards_per_target),
            'completion_rate': _round(row.completion_rate, 4),
            'league_yards_per_game': _round(row.league_yards_per_game),
            'league_yards_per_target': _round(row.league_yards_per_target),
            'league_completion_rate': _round(row.league_completion_rate, 4),
            'rank': None if pd.isna(row.rank) else int(row.rank),
            'of': int(row.of),
        })
    return out


def _round(value, digits: int = 2):
    return None if value is None or pd.isna(value) else round(float(value), digits)


def _role_table_cached(season: int | None) -> pd.DataFrame:
    return cached(f"defense_role_table:{season}", lambda: defense_role_table(season))
