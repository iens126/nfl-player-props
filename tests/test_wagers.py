"""Tests for the account-pick rules.

Two things are being defended here, and they are different in kind.

Grading is a *shared specification*: the browser settles local picks in
TypeScript and this job settles ranked picks in Python, and a user must never
see one answer on their picks page and another on the leaderboard. Both suites
read frontend/src/lib/grading.fixture.json, so a change to either implementation
that isn't a change to the spec fails on one side or the other.

Pricing is the *trust boundary*: quote() is what stands between "a bold pick"
and "an invented one", so the cases below are mostly about refusal — a line no
book posts, a side no book prices, a game the books don't list.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import wagers  # noqa: E402

FIXTURE = json.loads((ROOT / 'frontend/src/lib/grading.fixture.json').read_text())


# ---------------------------------------------------------------------------
# The shared settlement specification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('case', FIXTURE['cases'], ids=lambda c: c['name'])
def test_settlement_matches_the_shared_spec(case):
    result = wagers.settle(
        side=case['side'], line=case['line'], stake=case['stake'],
        price=case['price'], actual=case['actual'],
    )
    assert result['status'] == case['status']
    assert result['profit'] == pytest.approx(case['profit'], abs=0.01)


def test_profit_for_matches_american_odds_convention():
    assert wagers.profit_for(100, -110) == pytest.approx(90.909, abs=0.001)
    assert wagers.profit_for(100, +150) == pytest.approx(150.0)
    assert wagers.profit_for(10, 0) == 0.0


def test_implied_probability_is_symmetric_around_even_money():
    assert wagers.implied_probability(100) == pytest.approx(0.5)
    assert wagers.implied_probability(-100) == pytest.approx(0.5)
    assert wagers.implied_probability(0) is None


# ---------------------------------------------------------------------------
# Best price across books
# ---------------------------------------------------------------------------

BOOKS = [
    {'book': 'DraftKings', 'line': 60.5, 'over_price': -115, 'under_price': -105},
    {'book': 'FanDuel', 'line': 60.5, 'over_price': -108, 'under_price': -112},
    {'book': 'BetMGM', 'line': 62.5, 'over_price': +105, 'under_price': -130},
]


def test_best_price_takes_the_friendliest_book_at_that_exact_line():
    price, book = wagers._best_price(BOOKS, 'over', 60.5)
    assert (price, book) == (-108, 'FanDuel')


def test_best_price_does_not_borrow_a_price_from_a_different_line():
    # BetMGM's +105 is for 62.5. Offering it on 60.5 would hand out a price
    # nobody posted, which is exactly the cheat this module exists to stop.
    price, _ = wagers._best_price(BOOKS, 'over', 61.5)
    assert price is None


def test_best_price_ignores_a_book_missing_that_side():
    books = [{'book': 'DraftKings', 'line': 20.5, 'over_price': None, 'under_price': -120}]
    assert wagers._best_price(books, 'over', 20.5)[0] is None
    assert wagers._best_price(books, 'under', 20.5)[0] == -120


# ---------------------------------------------------------------------------
# quote(): what may be picked
# ---------------------------------------------------------------------------

MAIN = {
    'status': 'ok',
    'books': BOOKS,
    'event_id': 'evt1',
    'event': {
        'home_team': 'Seattle Seahawks', 'away_team': 'New England Patriots',
        'commence_time': '2026-09-14T20:05:00Z',
    },
}

LADDER = {
    'status': 'ok',
    'lines': [
        {'line': 40.5, 'books': [{'book': 'DraftKings', 'over_price': -260, 'under_price': +200}]},
        {'line': 99.5, 'books': [{'book': 'DraftKings', 'over_price': +420, 'under_price': -600}]},
    ],
}


def _quote(**kwargs):
    defaults = dict(player='Jaxon Smith-Njigba', team='SEA', opponent='NE',
                    stat='receiving_yards', side='over', line=60.5)
    return wagers.quote(**{**defaults, **kwargs})


def test_quote_prices_a_main_line_and_carries_the_kickoff():
    with mock.patch.object(wagers.odds_api, 'player_prop', return_value=MAIN):
        result = _quote()
    assert result['price'] == -108
    assert result['book'] == 'FanDuel'
    assert result['source'] == 'main'
    # The deadline and the price come from one response, so they cannot disagree.
    assert result['commence_time'] == '2026-09-14T20:05:00Z'


def test_quote_falls_back_to_the_alternate_ladder():
    with mock.patch.object(wagers.odds_api, 'player_prop', return_value=MAIN), \
         mock.patch.object(wagers.odds_api, 'alternate_lines', return_value=LADDER):
        result = _quote(line=99.5)
    assert (result['price'], result['source']) == (420, 'alternate')


def test_quote_refuses_a_line_no_book_is_posting():
    with mock.patch.object(wagers.odds_api, 'player_prop', return_value=MAIN), \
         mock.patch.object(wagers.odds_api, 'alternate_lines', return_value=LADDER):
        with pytest.raises(wagers.WagerError) as excinfo:
            _quote(line=0.5)
    assert excinfo.value.code == 'no_line'


def test_quote_refuses_when_the_books_do_not_list_the_game():
    absent = {'status': 'no_event', 'message': 'No upcoming SEA vs NE game listed by the books.'}
    with mock.patch.object(wagers.odds_api, 'player_prop', return_value=absent):
        with pytest.raises(wagers.WagerError) as excinfo:
            _quote()
    assert excinfo.value.code == 'no_event'


def test_quote_refuses_a_side_that_is_neither_over_nor_under():
    with pytest.raises(wagers.WagerError) as excinfo:
        _quote(side='maybe')
    assert excinfo.value.code == 'bad_side'
