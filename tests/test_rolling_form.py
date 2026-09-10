"""The rolling form: a new season's games join the list one at a time.

Offline - career and team data are patched - so these pin the rule itself. A
player who hasn't played yet this season is described by last season; one who
has played once gets that game added to the end of the same list, and the
oldest game makes room. Defenses work the same way, so at kickoff every team
still has a full season's sample rather than the two that have played.
"""

import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import data_loader as dl  # noqa: E402
from core.ml_model import _defense_game_index, _rolling_def_allowed  # noqa: E402

CAREER_COLUMNS = [
    'player_display_name', 'position', 'season', 'week', 'season_type',
    'team', 'opponent_team', 'receiving_yards',
]


def _games(name, season, weeks, base=50.0, team='KC', opponent='SEA'):
    return [(name, 'WR', season, w, 'REG', team, opponent, base + w) for w in weeks]


def _career(rows):
    return pd.DataFrame(rows, columns=CAREER_COLUMNS)


def _find(frame, name):
    dl.clear_cache()
    with mock.patch.object(dl, 'load_career_data', return_value=frame):
        try:
            return dl.find_player(name)
        finally:
            dl.clear_cache()


# -- players ------------------------------------------------------------------

def test_no_games_this_season_means_last_seasons_form():
    form = _find(_career(_games('A', 2025, range(1, 19))), 'A')
    assert len(form) == dl.ROLLING_GAMES
    assert set(form['season']) == {2025}
    assert (form['season'].iloc[-1], form['week'].iloc[-1]) == (2025, 18)


def test_one_game_this_season_is_added_to_the_end():
    everything = [(2025, w) for w in range(1, 19)] + [(2026, 1)]
    frame = _career(_games('A', 2025, range(1, 19)) + _games('A', 2026, [1], base=100.0))
    form = _find(frame, 'A')

    assert len(form) == dl.ROLLING_GAMES
    assert (form['season'].iloc[-1], form['week'].iloc[-1]) == (2026, 1)
    # ...and the oldest game made room for it.
    assert (form['season'].iloc[0], form['week'].iloc[0]) == everything[-dl.ROLLING_GAMES]


def test_players_without_a_game_this_season_are_still_listed():
    """At kickoff only two teams have played; everyone else must stay listed."""
    from backend import main

    roster = pd.DataFrame(
        {'team': ['KC', 'SEA', 'KC'], 'position': ['WR', 'WR', 'WR']},
        index=pd.Index(['Old Hand', 'Opener', 'Rookie'], name='full_name'),
    )
    career = _career(_games('Old Hand', 2025, [1]) + _games('Opener', 2026, [1]))
    with mock.patch.object(main, 'load_current_rosters', return_value=roster), \
            mock.patch.object(main, 'load_career_data', return_value=career), \
            mock.patch.object(main, 'calendar_season', return_value=2026):
        names = [p.name for p in main.list_players(team=None, position=None, q=None, limit=1000)]

    # The rookie has no NFL games yet, so there is nothing to analyse.
    assert names == ['Old Hand', 'Opener']


# -- defenses -----------------------------------------------------------------

def _team_rows(season, weeks, offense, defense):
    return [
        {'season': season, 'week': w, 'team': offense, 'opponent_team': defense, 'passing_yards': 200.0 + w}
        for w in weeks
    ]


def test_defense_window_takes_this_seasons_game_and_keeps_last_seasons_rest():
    frame = pd.DataFrame(
        _team_rows(2025, range(1, 19), 'NE', 'SEA')
        + _team_rows(2025, range(1, 19), 'SEA', 'KC')
        + _team_rows(2026, [1], 'NE', 'SEA')
    )
    dl.clear_cache()
    with mock.patch.object(dl, 'load_recent_team_data', return_value=frame):
        try:
            window = dl.recent_defense_rows()
        finally:
            dl.clear_cache()

    played = window[window['opponent_team'] == 'SEA']   # SEA's defense has played in 2026
    waiting = window[window['opponent_team'] == 'KC']   # KC's hasn't yet
    assert len(played) == len(waiting) == dl.ROLLING_GAMES
    assert (played['season'].iloc[-1], played['week'].iloc[-1]) == (2026, 1)
    assert set(waiting['season']) == {2025}


def test_missing_new_season_file_still_loads_last_season():
    def loader(year):
        if year == 2026:
            raise ConnectionError("404")
        return pd.DataFrame(_team_rows(2025, [1, 2], 'NE', 'SEA'))

    dl.clear_cache()
    with mock.patch.object(dl, 'calendar_season', return_value=2026), \
            mock.patch.object(dl, 'load_team_data', side_effect=loader):
        try:
            frame = dl.load_recent_team_data()
        finally:
            dl.clear_cache()
    assert set(frame['season']) == {2025}


# -- the trained model's matchup feature -----------------------------------------

def test_week_one_matchup_feature_uses_last_seasons_games():
    """It used to reset every season, leaving week 1 with nothing behind it."""
    rows = _games('P', 2025, range(1, 19), base=0.0) + _games('P', 2026, [1], base=100.0)
    df = _career(rows)[['opponent_team', 'position', 'season', 'week', 'receiving_yards']]
    allowed = _rolling_def_allowed(df, 'receiving_yards', _defense_game_index(df))

    window = dl.ROLLING_GAMES
    previous = [float(w) for w in range(1, 19)][-window:]
    assert allowed[-1] == pytest.approx(sum(previous) / len(previous))
    # A game never counts toward its own feature, so the very first has none.
    assert np.isnan(allowed[0])
