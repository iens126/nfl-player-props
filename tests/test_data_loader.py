"""Tests for which season the season-scoped loaders resolve to.

Offline: nflreadpy is patched, so these pin the rollover rule itself rather
than whatever week of the season it happens to be when they run.
"""

import sys
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import data_loader as dl  # noqa: E402


def _team_stats(teams, games_each=1):
    return pd.DataFrame({
        'team': [t for t in teams for _ in range(games_each)],
        'season_type': 'REG',
    })


def _resolve(current_frame):
    """stats_season() with the calendar at 2026 and `current_frame` as its stats."""
    dl.clear_cache()
    loader = mock.Mock(side_effect=lambda year: mock.Mock(to_pandas=lambda: current_frame))
    if isinstance(current_frame, Exception):
        loader = mock.Mock(side_effect=current_frame)
    with mock.patch.object(dl.nfl, 'get_current_season', return_value=2026), \
            mock.patch.object(dl.nfl, 'load_team_stats', loader):
        try:
            return dl.stats_season()
        finally:
            dl.clear_cache()


ALL_TEAMS = [f'T{i:02d}' for i in range(dl.NFL_TEAMS)]


def test_opening_night_keeps_last_season():
    """Two teams have played - the league is still described by last season."""
    assert _resolve(_team_stats(['SEA', 'NE'])) == 2025


def test_new_season_takes_over_once_every_team_has_played():
    assert _resolve(_team_stats(ALL_TEAMS)) == 2026


def test_postseason_games_do_not_count_toward_the_rollover():
    frame = _team_stats(['SEA', 'NE'])
    frame = pd.concat([frame, pd.DataFrame({'team': ALL_TEAMS, 'season_type': 'POST'})])
    assert _resolve(frame) == 2025


def test_missing_season_file_falls_back():
    """Before the opener nflverse may have nothing for the new season at all."""
    assert _resolve(ConnectionError("404")) == 2025
    assert _resolve(pd.DataFrame()) == 2025


def test_explicit_year_bypasses_the_resolver():
    dl.clear_cache()
    with mock.patch.object(dl, 'stats_season') as resolver, \
            mock.patch.object(dl.nfl, 'load_team_stats') as loader:
        dl.load_team_data(2019)
    resolver.assert_not_called()
    loader.assert_called_once_with(2019)
    dl.clear_cache()
