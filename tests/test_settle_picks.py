"""Tests for the nightly settlement job.

Two things here are easy to get wrong and expensive when wrong.

**Which day a game was played.** An 8:20pm Eastern Sunday kickoff is already
Monday in UTC. Comparing UTC dates puts every night game on the wrong day,
which would settle the pick against the wrong week — or not at all.

**Whether a missing stat line means "didn't play" or "not published yet".**
Both look identical in the data. Voiding too early refunds a pick that actually
lost; never voiding leaves inactive players pending forever.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import settle_picks  # noqa: E402

SCHEDULE = [
    {'season': 2026, 'week': 3, 'gameday': datetime(2026, 9, 20).date(),
     'home_team': 'SEA', 'away_team': 'NE'},
    {'season': 2026, 'week': 4, 'gameday': datetime(2026, 9, 27).date(),
     'home_team': 'NE', 'away_team': 'BUF'},
]

# Sunday 20 September, 8:20pm Eastern — which is 00:20 UTC on the 21st.
NIGHT_GAME = datetime(2026, 9, 21, 0, 20, tzinfo=timezone.utc)


def test_resolve_week_uses_eastern_dates_for_night_games():
    # The naive UTC date here is the 21st, which matches no game at all.
    assert settle_picks.resolve_week(SCHEDULE, 2026, 'SEA', 'NE', NIGHT_GAME) == 3


def test_resolve_week_falls_back_to_the_matchup_when_a_game_is_moved():
    # Flex scheduling and weather move kickoffs after a pick is taken. Within
    # one season the matchup is unambiguous, so it wins over the date.
    moved = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)
    assert settle_picks.resolve_week(SCHEDULE, 2026, 'NE', 'BUF', moved) == 4


def test_resolve_week_returns_none_for_a_matchup_that_is_not_scheduled():
    assert settle_picks.resolve_week(SCHEDULE, 2026, 'KC', 'DAL', NIGHT_GAME) is None


@pytest.fixture
def bundle(tmp_path):
    """A miniature data bundle in the same shape scripts/precompute.py writes."""
    (tmp_path / 'index.json').write_text(json.dumps({
        'players': [{'name': 'Jaxon Smith-Njigba', 'slug': 'jaxon-smith-njigba',
                     'team': 'SEA', 'position': 'WR'}],
    }))
    players = tmp_path / 'players'
    players.mkdir()
    (players / 'jaxon-smith-njigba.json').write_text(json.dumps({
        'summary': {},
        'games': [{'season': 2026, 'week': 3, 'receiving_yards': 91, 'receptions': 7}],
    }))
    return tmp_path


def pick(**over):
    base = {
        'id': 'pick-1', 'player': 'Jaxon Smith-Njigba', 'team': 'SEA', 'opponent': 'NE',
        'stat': 'receiving_yards', 'line': '60.5', 'side': 'over', 'stake': '10',
        'price': -110, 'season': 2026, 'kickoff': NIGHT_GAME.isoformat(),
    }
    return {**base, **over}


def run(bundle_dir, picks, now):
    """Run main() with the network stubbed out, returning the settle_pick calls."""
    calls = []

    def record(name, payload):
        calls.append((name, payload))
        return 200, {}

    class FrozenDatetime(settle_picks.datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with mock.patch.object(settle_picks.supabase, 'configured', return_value=True), \
         mock.patch.object(settle_picks.supabase, 'select', return_value=picks), \
         mock.patch.object(settle_picks.supabase, 'rpc', side_effect=record), \
         mock.patch.object(settle_picks, 'load_schedule', return_value=SCHEDULE), \
         mock.patch.object(settle_picks, 'datetime', FrozenDatetime), \
         mock.patch.object(sys, 'argv', ['settle_picks', '--bundle', str(bundle_dir)]):
        exit_code = settle_picks.main()

    return exit_code, calls


def test_a_played_game_settles_against_the_real_stat_line(bundle):
    code, calls = run(bundle, [pick()], NIGHT_GAME + timedelta(hours=12))
    assert code == 0
    assert len(calls) == 1
    name, payload = calls[0]
    assert name == 'settle_pick'
    # 91 receiving yards clears 60.5. The job reports what it saw; the database
    # works out what that paid.
    assert payload['p_status'] == 'hit'
    assert payload['p_actual'] == 91.0
    assert payload['p_week'] == 3
    assert 'p_profit' not in payload


def test_an_under_that_missed_is_reported_as_a_miss(bundle):
    code, calls = run(bundle, [pick(side='under')], NIGHT_GAME + timedelta(hours=12))
    assert code == 0
    assert calls[0][1]['p_status'] == 'miss'


def test_a_missing_stat_line_waits_before_voiding(bundle):
    # nflverse publishes a day or two behind. Voiding here would refund a pick
    # that may well have lost.
    absent = pick(player='Somebody Else')
    code, calls = run(bundle, [absent], NIGHT_GAME + timedelta(hours=6))
    assert code == 0
    assert calls == []


def test_a_missing_stat_line_voids_once_the_grace_window_has_passed(bundle):
    absent = pick(player='Somebody Else')
    code, calls = run(bundle, [absent], NIGHT_GAME + settle_picks.GRACE + timedelta(hours=1))
    assert code == 0
    assert calls[0][1]['p_status'] == 'void'
    assert calls[0][1]['p_actual'] is None


def test_a_dry_run_writes_nothing(bundle):
    calls = []
    with mock.patch.object(settle_picks.supabase, 'configured', return_value=True), \
         mock.patch.object(settle_picks.supabase, 'select', return_value=[pick()]), \
         mock.patch.object(settle_picks.supabase, 'rpc', side_effect=lambda *a: calls.append(a)), \
         mock.patch.object(settle_picks, 'load_schedule', return_value=SCHEDULE), \
         mock.patch.object(sys, 'argv',
                           ['settle_picks', '--bundle', str(bundle), '--dry-run']):
        assert settle_picks.main() == 0
    assert calls == []
