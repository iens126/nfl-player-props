"""Tests for the role-based defense breakdown.

The panel this feeds is descriptive by design - role-specific defensive
performance was measured and does not persist - so what matters here is that
the counting is right and the labels mean what they say.
"""

import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import defense_roles as dr  # noqa: E402


def _play(game, week, defteam, posteam, receiver, yards, complete=1.0):
    return {
        'game_id': game, 'week': week, 'season': 2025, 'season_type': 'REG',
        'defteam': defteam, 'posteam': posteam, 'pass_attempt': 1.0,
        'receiver_player_id': receiver, 'yards_gained': yards, 'complete_pass': complete,
    }


# Two WRs and a TE on one offense; the WR with more targets is the WR1, and the
# tight end is TE1 even though he is targeted less than either receiver.
POSITIONS = {'wr_a': 'WR', 'wr_b': 'WR', 'te_a': 'TE', 'rb_a': 'RB'}

def _frame():
    rows = []
    for week in range(1, 13):                       # 12 games
        rows += [_play(f'g{week}', week, 'BAL', 'NYG', 'wr_a', 20)] * 2   # 24 targets
        rows.append(_play(f'g{week}', week, 'BAL', 'NYG', 'wr_b', 10))    # 12 targets
        rows.append(_play(f'g{week}', week, 'BAL', 'NYG', 'te_a', 5))     # 12 targets
    return pd.DataFrame(rows)


@pytest.fixture
def patched():
    with mock.patch.object(dr, 'load_pbp_data', return_value=_frame()), \
         mock.patch.object(dr, 'load_player_positions', return_value=POSITIONS), \
         mock.patch.object(dr, 'cached', lambda key, loader: loader()):
        yield


def test_roles_are_ranked_within_position(patched):
    table = dr.defense_role_table()
    labels = {(r.position, r.role) for r in table.itertuples()}
    # The tight end is TE1, not TE3 - ranking is per position, not across all
    # pass catchers, which is what makes "WR1" mean a team's top receiver.
    assert ('TE', 1.0) in labels
    assert ('WR', 1.0) in labels
    assert ('WR', 2.0) in labels


def test_the_busier_receiver_is_wr1(patched):
    rows = dr.defense_roles('BAL')
    wr1 = next(r for r in rows if r['label'] == 'WR1')
    assert wr1['targets'] == 24          # wr_a, two per game
    assert wr1['yards'] == 480.0


def test_per_game_and_per_target_rates(patched):
    rows = dr.defense_roles('BAL')
    wr1 = next(r for r in rows if r['label'] == 'WR1')
    assert wr1['games'] == 12
    assert wr1['yards_per_game'] == pytest.approx(40.0)
    assert wr1['yards_per_target'] == pytest.approx(20.0)
    assert wr1['completion_rate'] == pytest.approx(1.0)


def test_sample_size_is_reported(patched):
    """Every row carries games and targets, so a thin row reads as thin."""
    for row in dr.defense_roles('BAL'):
        assert row['games'] > 0
        assert row['targets'] > 0
        assert 'rank' in row and 'of' in row


def test_low_volume_receivers_are_excluded(patched):
    """A player with a couple of targets shouldn't be ranked as someone's WR2."""
    frame = _frame()
    frame = pd.concat([frame, pd.DataFrame([
        _play('g1', 1, 'BAL', 'NYG', 'scrub', 80),
    ])], ignore_index=True)
    positions = {**POSITIONS, 'scrub': 'WR'}
    with mock.patch.object(dr, 'load_pbp_data', return_value=frame), \
         mock.patch.object(dr, 'load_player_positions', return_value=positions), \
         mock.patch.object(dr, 'cached', lambda key, loader: loader()):
        rows = dr.defense_roles('BAL')
    # One target is below MIN_SEASON_TARGETS, so no WR3 appears at all.
    assert not any(r['label'] == 'WR3' for r in rows)


def test_unknown_team_returns_nothing(patched):
    assert dr.defense_roles('KC') == []


def test_empty_play_by_play_is_survivable():
    with mock.patch.object(dr, 'load_pbp_data', return_value=pd.DataFrame()), \
         mock.patch.object(dr, 'load_player_positions', return_value={}), \
         mock.patch.object(dr, 'cached', lambda key, loader: loader()):
        assert dr.defense_roles('BAL') == []
