"""The persistent snapshot cache and the credit reserve.

Both exist for one reason: 500 credits a month is ample if a response is paid
for once, and gone in a fortnight if it is paid for on every cold start. So the
things worth pinning are that a second caller doesn't spend a credit, that a
snapshot reports its real age rather than claiming to be fresh, and that when
the reserve is reached it is browsing that gives way and never pricing.
"""

import sys
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import odds  # noqa: E402


class FakeStore:
    """A store that counts what it is asked to do."""

    def __init__(self, remaining=None):
        self.rows: dict[str, tuple[float, object]] = {}
        self._remaining = remaining
        self.writes = 0

    def get(self, key):
        return self.rows.get(key)

    def put(self, key, value, fetched_at):
        self.rows[key] = (fetched_at, value)
        self.writes += 1

    def remaining(self):
        return self._remaining

    def record_remaining(self, value):
        self._remaining = int(value)


@pytest.fixture
def store():
    odds.clear_cache()
    fake = FakeStore()
    odds.set_store(fake)
    yield fake
    odds.set_store(odds._NoStore())
    odds.clear_cache()


def counting_loader(value='payload'):
    calls = []

    def load():
        calls.append(1)
        return value

    return load, calls


# ---------------------------------------------------------------------------
# Reading through
# ---------------------------------------------------------------------------

def test_a_miss_calls_the_provider_and_persists_it(store):
    load, calls = counting_loader()
    value, fetched_at = odds._cached('k', load)
    assert value == 'payload'
    assert len(calls) == 1
    assert store.rows['k'][1] == 'payload'
    assert fetched_at == pytest.approx(time.time(), abs=5)


def test_a_second_process_pays_nothing(store):
    """The case that matters. Two cold starts, one credit."""
    load, calls = counting_loader()
    odds._cached('k', load)
    odds.clear_cache()  # a fresh serverless process: memory gone, store intact

    load2, calls2 = counting_loader()
    value, _ = odds._cached('k', load2)
    assert value == 'payload'
    assert calls2 == []


def test_a_snapshot_reports_when_it_was_fetched_not_when_it_was_read(store):
    """The freshness line on screen is only worth anything if this is true."""
    earlier = time.time() - 300
    store.rows['k'] = (earlier, 'payload')
    load, calls = counting_loader()
    _, fetched_at = odds._cached('k', load)
    assert fetched_at == pytest.approx(earlier, abs=1)
    assert calls == []


def test_a_stale_snapshot_is_refetched(store):
    store.rows['k'] = (time.time() - odds.CACHE_MINUTES * 60 - 60, 'old')
    load, calls = counting_loader('new')
    value, _ = odds._cached('k', load)
    assert (value, len(calls)) == ('new', 1)


def test_a_store_that_fails_to_write_still_serves_the_call(store):
    """A cache outage must cost a credit, not the response."""
    with mock.patch.object(store, 'put', side_effect=RuntimeError('down')):
        load, _ = counting_loader()
        value, _ = odds._cached('k', load)
    assert value == 'payload'


# ---------------------------------------------------------------------------
# The reserve
# ---------------------------------------------------------------------------

def test_not_conserving_without_a_credit_count(store):
    """An unknown balance must not shut browsing down."""
    assert odds.credits_remaining() is None
    assert odds.conserving() is False


def test_conserving_below_the_reserve(store):
    store._remaining = odds.RESERVE_CREDITS
    assert odds.conserving() is True
    store._remaining = odds.RESERVE_CREDITS + 1
    assert odds.conserving() is False


def test_browsing_serves_a_stale_snapshot_rather_than_spending(store):
    store._remaining = 1
    store.rows['k'] = (time.time() - 86_400, 'yesterday')
    load, calls = counting_loader('fresh')
    value, fetched_at = odds._cached('k', load)
    assert (value, calls) == ('yesterday', [])
    # And it still admits how old it is, so the page can say so.
    assert time.time() - fetched_at == pytest.approx(86_400, abs=5)


def test_browsing_refuses_when_there_is_nothing_to_serve(store):
    store._remaining = 1
    load, calls = counting_loader()
    with pytest.raises(odds.Conserving):
        odds._cached('k', load)
    assert calls == []


def test_pricing_spends_the_reserve(store):
    """The whole point of holding credits back: this call still goes live."""
    store._remaining = 1
    store.rows['k'] = (time.time() - 86_400, 'yesterday')
    load, calls = counting_loader('fresh')
    value, _ = odds._cached('k', load, essential=True)
    assert (value, len(calls)) == ('fresh', 1)


def test_pricing_is_never_refused_for_want_of_a_snapshot(store):
    store._remaining = 0
    load, calls = counting_loader('fresh')
    value, _ = odds._cached('k', load, essential=True)
    assert (value, len(calls)) == ('fresh', 1)


# ---------------------------------------------------------------------------
# How fresh a snapshot has to be
# ---------------------------------------------------------------------------

def test_browsing_accepts_a_snapshot_up_to_the_cache_window(store):
    store.rows['k'] = (time.time() - odds.CACHE_MINUTES * 60 + 30, 'cached')
    load, calls = counting_loader('fresh')
    value, _ = odds._cached('k', load)
    assert (value, calls) == ('cached', [])


def test_pricing_refuses_a_snapshot_browsing_would_have_accepted(store):
    """The bug this closes: a pick written at a half-hour-old price.

    `essential` used to mean only "may spend the reserve", so a pricing call
    took whatever browsing would have taken — and raising ODDS_CACHE_MINUTES
    silently widened the window a pick could be priced in. Freshness is now its
    own bound, so the same snapshot browsing is happy with sends pricing back to
    the provider.
    """
    age = odds.PRICING_MAX_AGE_SECONDS + 60
    assert age < odds.CACHE_MINUTES * 60, 'the windows must differ for this to mean anything'

    store.rows['props:evt:mkt'] = (time.time() - age, ('old', '400'))
    load, calls = counting_loader(('fresh', '399'))

    # Browsing is content with it...
    value, _ = odds._cached('props:evt:mkt', load)
    assert (value, calls) == (('old', '400'), [])

    # ...and pricing is not.
    odds.clear_cache()
    value, _ = odds._cached('props:evt:mkt', load, essential=True,
                            max_age=odds.PRICING_MAX_AGE_SECONDS)
    assert (value, len(calls)) == (('fresh', '399'), 1)


def test_pricing_still_reuses_a_genuinely_recent_snapshot(store):
    """Tight, not zero: a pick placed moments after another must not re-pay."""
    store.rows['props:evt:mkt'] = (time.time() - 5, ('recent', '400'))
    load, calls = counting_loader(('fresh', '399'))
    value, _ = odds._cached('props:evt:mkt', load, essential=True,
                            max_age=odds.PRICING_MAX_AGE_SECONDS)
    assert (value, calls) == (('recent', '400'), [])


def test_fetch_market_applies_the_short_window_only_when_pricing(store):
    """The wiring, not just the primitive: _fetch_market picks the bound."""
    seen = []

    def fake_cached(key, loader, essential=False, max_age=None):
        seen.append((essential, max_age))
        return ({'bookmakers': []}, '400'), time.time()

    with mock.patch.object(odds, '_cached', fake_cached):
        odds._fetch_market('evt', 'mkt')
        odds._fetch_market('evt', 'mkt', essential=True)

    assert seen == [(False, None), (True, odds.PRICING_MAX_AGE_SECONDS)]


def test_listing_events_keeps_the_long_window(store):
    """Essential, but for the other reason.

    list_events() is essential because it must never be refused, not because it
    must be seconds old — it is unbilled and changes hourly. Tying freshness to
    the same flag would have it re-fetch on every board load.
    """
    store.rows['events'] = (time.time() - odds.PRICING_MAX_AGE_SECONDS - 60, [{'id': 'e'}])
    calls = []

    def _get(path, params):
        calls.append(path)
        return [{'id': 'fresh'}], '400'

    with mock.patch.object(odds, '_get', _get):
        assert odds.list_events() == [{'id': 'e'}]
    assert calls == []


def test_the_credit_count_is_recorded_from_the_response_header(store):
    class Response:
        headers = {'x-requests-remaining': '317'}
        status = 200

        def read(self): return b'{"ok": true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with mock.patch.object(odds.urllib.request, 'urlopen', return_value=Response()), \
         mock.patch.object(odds, 'api_key', return_value='k'):
        odds._get('/x', {})
    assert store.remaining() == 317


def test_no_store_behaves_exactly_as_before():
    """Without Supabase this module must be what it always was."""
    odds.set_store(odds._NoStore())
    odds.clear_cache()
    load, calls = counting_loader()
    odds._cached('k', load)
    odds.clear_cache()
    odds._cached('k', load)
    assert len(calls) == 2          # no persistence, so the credit is spent twice
    assert odds.conserving() is False
