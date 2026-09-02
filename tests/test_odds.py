"""Tests for the sportsbook odds client.

This code path only executes when an ODDS_API_KEY is configured, which means it
would otherwise ship unexercised and fail the first time a real key was added.
The provider's response shape is pinned here from its published documentation
so the parsing, the player matching, and every degraded path are covered
without needing a key or a network call.
"""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import odds  # noqa: E402

# Shaped exactly like a /events/{id}/odds response for a player-props market.
SAMPLE_ODDS = {
    'id': 'evt1',
    'home_team': 'Seattle Seahawks',
    'away_team': 'New England Patriots',
    'commence_time': '2026-09-14T20:05:00Z',
    'bookmakers': [
        {
            'key': 'draftkings', 'title': 'DraftKings',
            'markets': [{
                'key': 'player_reception_yds', 'last_update': '2026-09-14T18:00:00Z',
                'outcomes': [
                    {'name': 'Over', 'description': 'Jaxon Smith-Njigba', 'price': -115, 'point': 78.5},
                    {'name': 'Under', 'description': 'Jaxon Smith-Njigba', 'price': -105, 'point': 78.5},
                    {'name': 'Over', 'description': 'Cooper Kupp', 'price': 100, 'point': 45.5},
                ],
            }],
        },
        {
            'key': 'fanduel', 'title': 'FanDuel',
            'markets': [{
                'key': 'player_reception_yds', 'last_update': '2026-09-14T18:02:00Z',
                'outcomes': [
                    {'name': 'Over', 'description': 'Jaxon Smith-Njigba', 'price': -110, 'point': 80.5},
                    {'name': 'Under', 'description': 'Jaxon Smith-Njigba', 'price': -110, 'point': 80.5},
                ],
            }],
        },
    ],
}

SAMPLE_EVENTS = [{
    'id': 'evt1', 'home_team': 'Seattle Seahawks', 'away_team': 'New England Patriots',
    'commence_time': '2026-09-14T20:05:00Z',
}]


def _patched(get_result, key='test-key'):
    """Run the client with a stubbed transport and a configured key."""
    odds.clear_cache()

    def fake_get(path, params):
        if path.endswith('/events'):
            return SAMPLE_EVENTS, '480'
        return get_result, '479'

    return mock.patch.object(odds, '_get', side_effect=fake_get), mock.patch.dict(
        odds.os.environ, {odds.ODDS_API_KEY_ENV: key}
    )


def test_missing_key_degrades_with_a_message():
    odds.clear_cache()
    with mock.patch.dict(odds.os.environ, {odds.ODDS_API_KEY_ENV: ''}):
        result = odds.player_prop('Anyone', 'SEA', 'NE', 'receiving_yards')
    assert result['status'] == 'not_configured'
    assert result['books'] == []
    assert 'the-odds-api.com' in result['message']


def test_parses_both_books_for_the_right_player():
    get_patch, env_patch = _patched(SAMPLE_ODDS)
    with get_patch, env_patch:
        result = odds.player_prop('Jaxon Smith-Njigba', 'SEA', 'NE', 'receiving_yards')

    assert result['status'] == 'ok'
    assert [b['book'] for b in result['books']] == ['DraftKings', 'FanDuel']

    dk = result['books'][0]
    assert dk['line'] == 78.5
    assert dk['over_price'] == -115
    assert dk['under_price'] == -105
    # Cooper Kupp's line must not leak into another player's row.
    assert all(b['line'] in (78.5, 80.5) for b in result['books'])


def test_implied_probability_conversion():
    """American odds -> implied probability, including the book's margin."""
    assert abs(odds._american_to_implied(-110) - 0.5238) < 0.001
    assert abs(odds._american_to_implied(100) - 0.5) < 1e-9
    assert abs(odds._american_to_implied(150) - 0.4) < 1e-9
    assert abs(odds._american_to_implied(-200) - 0.6667) < 0.001
    assert odds._american_to_implied(None) is None

    # Both sides of a real market sum to more than 1 - that's the overround,
    # and the UI has to say so rather than presenting it as a true probability.
    both = odds._american_to_implied(-115) + odds._american_to_implied(-105)
    assert both > 1.0


def test_player_matching_is_case_and_space_insensitive():
    get_patch, env_patch = _patched(SAMPLE_ODDS)
    with get_patch, env_patch:
        result = odds.player_prop('  jaxon smith-njigba ', 'SEA', 'NE', 'receiving_yards')
    assert result['status'] == 'ok'
    assert len(result['books']) == 2


def test_unknown_player_reports_no_market_rather_than_empty():
    get_patch, env_patch = _patched(SAMPLE_ODDS)
    with get_patch, env_patch:
        result = odds.player_prop('Nobody At All', 'SEA', 'NE', 'receiving_yards')
    assert result['status'] == 'no_market'
    assert result['books'] == []
    assert 'Nobody At All' in result['message']


def test_unsupported_stat_is_reported():
    odds.clear_cache()
    with mock.patch.dict(odds.os.environ, {odds.ODDS_API_KEY_ENV: 'test-key'}):
        result = odds.player_prop('Anyone', 'SEA', 'NE', 'not_a_real_stat')
    assert result['status'] == 'no_market'


def test_matchup_without_a_listed_game():
    get_patch, env_patch = _patched(SAMPLE_ODDS)
    with get_patch, env_patch:
        result = odds.player_prop('Jaxon Smith-Njigba', 'KC', 'BUF', 'receiving_yards')
    assert result['status'] == 'no_event'
    assert result['books'] == []


def test_provider_failure_is_not_fatal():
    odds.clear_cache()
    with mock.patch.object(odds, '_get', side_effect=OSError('connection reset')), \
            mock.patch.dict(odds.os.environ, {odds.ODDS_API_KEY_ENV: 'test-key'}):
        result = odds.player_prop('Jaxon Smith-Njigba', 'SEA', 'NE', 'receiving_yards')
    assert result['status'] == 'error'
    assert result['books'] == []


def test_responses_are_cached_to_conserve_credits():
    """Player props bill per request, so a repeat lookup must not re-hit the API."""
    odds.clear_cache()
    calls = []

    def counting_get(path, params):
        calls.append(path)
        return (SAMPLE_EVENTS, '480') if path.endswith('/events') else (SAMPLE_ODDS, '479')

    with mock.patch.object(odds, '_get', side_effect=counting_get), \
            mock.patch.dict(odds.os.environ, {odds.ODDS_API_KEY_ENV: 'test-key'}):
        for _ in range(4):
            odds.player_prop('Jaxon Smith-Njigba', 'SEA', 'NE', 'receiving_yards')

    prop_calls = [c for c in calls if not c.endswith('/events')]
    assert len(prop_calls) == 1, f"expected 1 billed request, made {len(prop_calls)}"


def test_every_supported_stat_maps_to_a_market():
    from core.data_loader import bettable_columns
    unmapped = [s for s in bettable_columns if s not in odds.MARKET_BY_STAT]
    # Targets have no standard sportsbook market; everything else should map.
    assert unmapped == ['targets'], unmapped


def test_all_32_teams_resolve_to_a_name():
    from core.data_loader import load_team_data
    abbrs = set(load_team_data()['team'].dropna().unique())
    missing = sorted(a for a in abbrs if a not in odds.TEAM_NAMES)
    assert not missing, f"no sportsbook team name for: {missing}"


if __name__ == '__main__':
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
