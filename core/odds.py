"""Live sportsbook lines from The Odds API.

This is a browsing surface, not a bet recommender. It lists what the books are
currently offering so someone can spot a line worth a closer look and then go
read that player's history and projection. Nothing here scores, ranks, or
flags a line as good value - the user brings their own judgement and carries
all the risk.

Requires an API key in ODDS_API_KEY (https://the-odds-api.com - the free tier
is 500 credits/month). With no key configured, every call here returns a result
that says so rather than raising, so the rest of the app keeps working and the
UI can explain what's missing.

Credit discipline matters: player props are billed per event *per market*, so a
handful of page loads can burn a month of free quota. Responses are cached for
ODDS_CACHE_MINUTES (default 10), and because one request returns every player
in that game for that market, the whole board is served from the same single
credit that one player lookup would have cost.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

ODDS_API_KEY_ENV = "ODDS_API_KEY"
DEFAULT_BOOKMAKERS = "draftkings,fanduel,betmgm,caesars"
CACHE_MINUTES = float(os.environ.get("ODDS_CACHE_MINUTES", "10"))
REQUEST_TIMEOUT = 10

# Our stat keys -> The Odds API market keys.
MARKET_BY_STAT = {
    'passing_yards': 'player_pass_yds',
    'passing_tds': 'player_pass_tds',
    'attempts': 'player_pass_attempts',
    'completions': 'player_pass_completions',
    'passing_interceptions': 'player_pass_interceptions',
    'receiving_yards': 'player_reception_yds',
    'receptions': 'player_receptions',
    'receiving_tds': 'player_reception_tds',
    'rushing_yards': 'player_rush_yds',
    'carries': 'player_rush_attempts',
    'rushing_tds': 'player_rush_tds',
}

# Alternate markets carry the "X+" milestone ladder: the same player at several
# thresholds, each with its own price, which is what makes a line/price explorer
# possible. Not every stat has one, and coverage is thinner than the main line.
#
# These are billed separately - cost is markets x regions - so an alternate
# lookup is a second credit on top of the main line for that game. Nothing
# fetches them automatically; the UI asks only when a user opens the ladder.
ALTERNATE_MARKET_BY_STAT = {
    'passing_yards': 'player_pass_yds_alternate',
    'passing_tds': 'player_pass_tds_alternate',
    'receiving_yards': 'player_reception_yds_alternate',
    'receptions': 'player_receptions_alternate',
    'rushing_yards': 'player_rush_yds_alternate',
    'rushing_tds': 'player_rush_tds_alternate',
}

# The Odds API identifies teams by full name; we work in nflverse abbreviations.
TEAM_NAMES = {
    'ARI': 'Arizona Cardinals', 'ATL': 'Atlanta Falcons', 'BAL': 'Baltimore Ravens',
    'BUF': 'Buffalo Bills', 'CAR': 'Carolina Panthers', 'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals', 'CLE': 'Cleveland Browns', 'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos', 'DET': 'Detroit Lions', 'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans', 'IND': 'Indianapolis Colts', 'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs', 'LA': 'Los Angeles Rams', 'LAR': 'Los Angeles Rams',
    'LAC': 'Los Angeles Chargers', 'LV': 'Las Vegas Raiders', 'MIA': 'Miami Dolphins',
    'MIN': 'Minnesota Vikings', 'NE': 'New England Patriots', 'NO': 'New Orleans Saints',
    'NYG': 'New York Giants', 'NYJ': 'New York Jets', 'PHI': 'Philadelphia Eagles',
    'PIT': 'Pittsburgh Steelers', 'SEA': 'Seattle Seahawks', 'SF': 'San Francisco 49ers',
    'TB': 'Tampa Bay Buccaneers', 'TEN': 'Tennessee Titans', 'WAS': 'Washington Commanders',
}

# The Odds API names teams in full; the rest of the app works in nflverse
# abbreviations. First entry wins for the Rams, whose 'LA' spelling is the one
# nflverse uses in schedules and stat lines.
ABBR_BY_TEAM_NAME: dict[str, str] = {}
for _abbr, _full in TEAM_NAMES.items():
    ABBR_BY_TEAM_NAME.setdefault(_full, _abbr)


_NAME_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}


def normalize_player(name: str | None) -> str:
    """Casefold, drop punctuation and generational suffixes.

    The books and nflverse disagree on both - "Marvin Harrison Jr." against
    "Marvin Harrison", "A.J. Brown" against "AJ Brown". Matching on the raw
    string meant those players silently reported no line posted, which is
    indistinguishable from the book genuinely not offering one.
    """
    if not name:
        return ''
    cleaned = ''.join(c for c in str(name).lower() if c.isalnum() or c.isspace())
    return ' '.join(p for p in cleaned.split() if p not in _NAME_SUFFIXES)


def abbr_for_team_name(name: str | None) -> str | None:
    """nflverse abbreviation for a full team name, or None if unrecognised."""
    if not name:
        return None
    return ABBR_BY_TEAM_NAME.get(name.strip())


_cache: dict[str, tuple[float, object]] = {}

# ---------------------------------------------------------------------------
# The credit budget, and where snapshots live
# ---------------------------------------------------------------------------

# Below this many credits, browsing stops spending and serves whatever snapshot
# it has. Pricing a pick still goes live: it is rare, it is the one call that
# must not be wrong — a stale line is a bet the book is no longer offering —
# and holding credits back for it is the entire point of a reserve.
RESERVE_CREDITS = int(os.environ.get("ODDS_RESERVE_CREDITS", "50"))


class Conserving(Exception):
    """Raised instead of spending one of the last credits on a browsing call."""


class _NoStore:
    """No Supabase project: exactly the behaviour this module always had."""

    def get(self, key: str): return None
    def put(self, key: str, value: object, fetched_at: float) -> None: pass
    def remaining(self) -> int | None: return None
    def record_remaining(self, value) -> None: pass


_store: object = _NoStore()


def set_store(store) -> None:
    """Install a store that outlives the process.

    The dict above is close to useless in production and it is worth being
    blunt about why. These functions run as serverless handlers, so most
    requests get a cold process with an empty cache; the ten-minute window only
    ever helps the requests that happen to land on a warm instance. Every other
    one pays a credit for a response the service already had.

    Persisting the same responses turns a cache that mostly misses into one
    that mostly hits, which is the difference between 500 credits a month being
    ample and being gone inside a fortnight. The provider's terms permit
    storing their data; what they forbid is redistributing it as a data
    product, which this is not.

    Optional, like everything else here that wants Supabase.
    """
    global _store
    _store = store


def credits_remaining() -> int | None:
    """Credits left this billing period, as last reported by the provider."""
    return _store.remaining()


def conserving() -> bool:
    """Whether the reserve has been reached and browsing should stop spending."""
    left = credits_remaining()
    return left is not None and left <= RESERVE_CREDITS


def api_key() -> str | None:
    key = os.environ.get(ODDS_API_KEY_ENV, "").strip()
    return key or None


def is_configured() -> bool:
    return api_key() is not None


def _cached(key: str, loader, essential: bool = False):
    """Read through memory, then the store, then the provider.

    Returns (value, fetched_at). The timestamp is when the provider was asked,
    not when this returned — a snapshot handed back an hour later has to report
    its real age, or the freshness line on screen becomes a lie exactly when it
    matters most.

    `essential` marks a call that must not be served stale and must not be
    refused: pricing a pick. Everything else is browsing, and browsing is what
    gives way when the reserve is reached.
    """
    now = time.time()
    fresh_for = CACHE_MINUTES * 60

    entry = _cache.get(key)
    if entry is not None and (now - entry[0]) < fresh_for:
        return entry[1], entry[0]

    stale = entry
    stored = _store.get(key)
    if stored is not None:
        fetched_at, value = stored
        if (now - fetched_at) < fresh_for:
            _cache[key] = (fetched_at, value)
            return value, fetched_at
        if stale is None:
            stale = (fetched_at, value)

    # Nothing fresh. Browsing gives way to the reserve here; pricing does not.
    if not essential and conserving():
        if stale is not None:
            return stale[1], stale[0]
        raise Conserving()

    value = loader()
    _cache[key] = (now, value)
    try:
        _store.put(key, value, now)
    except Exception:  # noqa: BLE001 - a store that is down must not lose the call
        logger.warning("Could not persist an odds snapshot for %s", key)
    return value, now


def clear_cache():
    _cache.clear()


def _get(path: str, params: dict):
    params = {**params, 'apiKey': api_key()}
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        import json
        payload = json.loads(response.read().decode('utf-8'))
        remaining = response.headers.get('x-requests-remaining')
        # Recorded on every call, including the unbilled event listing, so the
        # reserve check has a number to work from after a cold start.
        if remaining is not None:
            try:
                _store.record_remaining(int(remaining))
            except Exception:  # noqa: BLE001
                logger.warning("Could not record the remaining credit count")
        return payload, remaining


def list_events():
    """Upcoming NFL events, so a matchup can be resolved to an event id."""
    def _load():
        events, _ = _get(f"/sports/{SPORT}/events", {})
        return events
    # Listing events is unbilled, so the reserve has no reason to block it.
    events, _fetched_at = _cached("events", _load, essential=True)
    return events


def _find_event(team_a: str, team_b: str):
    """The upcoming event featuring both teams, if there is one."""
    names = {TEAM_NAMES.get(team_a, team_a), TEAM_NAMES.get(team_b, team_b)}
    for event in list_events():
        if {event.get('home_team'), event.get('away_team')} == names:
            return event
    return None


def _american_to_implied(price) -> float | None:
    """Convert American odds to the probability they imply (with the book's margin)."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price == 0:
        return None
    return -price / (-price + 100.0) if price < 0 else 100.0 / (price + 100.0)


def upcoming_games() -> dict:
    """Games the books currently have listed, to choose a board from.

    Listing events is not billed against the props quota, so this is safe to
    call on every page load.
    """
    if not is_configured():
        return {
            'status': 'not_configured',
            'message': 'Live odds need an ODDS_API_KEY. Get a free key at the-odds-api.com.',
            'games': [],
        }
    try:
        events = list_events()
    except urllib.error.HTTPError as exc:
        return {'status': 'error', 'message': _http_message(exc), 'games': []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Odds event listing failed: %s", exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'games': []}

    games = [
        {
            'id': event.get('id'),
            'home_team': event.get('home_team'),
            'away_team': event.get('away_team'),
            'commence_time': event.get('commence_time'),
        }
        for event in events
        if event.get('id')
    ]
    games.sort(key=lambda g: g['commence_time'] or '')
    return {'status': 'ok', 'games': games}


# Shown when the reserve has been reached and there is no snapshot to fall back
# on. Deliberately explicit about the trade being made on the user's behalf.
CONSERVING_MESSAGE = (
    'Live odds are paused to keep the last few API credits for placing picks. '
    'They come back when the monthly quota resets.'
)

def _http_message(exc: urllib.error.HTTPError) -> str:
    if exc.code in (401, 403):
        return 'Invalid or expired API key.'
    if exc.code == 429:
        return 'Odds API quota exhausted for this billing period.'
    return f'Odds API error ({exc.code}).'


def _fetch_market(event_id: str, market: str, essential: bool = False):
    """One event's prices for one market. This is the billed call - 1 credit.

    Returns (payload, remaining, fetched_at), the last of which is when the
    provider was actually asked rather than when this was called.
    """
    def _load():
        return _get(
            f"/sports/{SPORT}/events/{event_id}/odds",
            {'regions': 'us', 'markets': market, 'oddsFormat': 'american',
             'bookmakers': DEFAULT_BOOKMAKERS},
        )
    (payload, remaining), fetched_at = _cached(
        f"props:{event_id}:{market}", _load, essential=essential,
    )
    return payload, remaining, fetched_at


def _collect_players(payload: dict, market: str) -> dict[str, list[dict]]:
    """Regroup the API's book-major response into player -> that player's prices."""
    by_player: dict[str, list[dict]] = {}

    for bookmaker in payload.get('bookmakers', []):
        for market_data in bookmaker.get('markets', []):
            if market_data.get('key') != market:
                continue

            # Player props carry the player's name in `description`, with the
            # over and under arriving as two separate outcomes.
            sides: dict[str, dict] = {}
            for outcome in market_data.get('outcomes', []):
                name = (outcome.get('description') or '').strip()
                if not name:
                    continue
                side = (outcome.get('name') or '').lower()
                if side not in ('over', 'under'):
                    continue
                sides.setdefault(name, {})[side] = outcome

            for name, pair in sides.items():
                over, under = pair.get('over'), pair.get('under')
                reference = over or under
                by_player.setdefault(name, []).append({
                    'book': bookmaker.get('title', bookmaker.get('key')),
                    'line': reference.get('point'),
                    'over_price': over.get('price') if over else None,
                    'under_price': under.get('price') if under else None,
                    'implied_over': _american_to_implied(over.get('price')) if over else None,
                    'implied_under': _american_to_implied(under.get('price')) if under else None,
                    'last_update': market_data.get('last_update'),
                })

    return by_player


def _consensus_line(books: list[dict]) -> float | None:
    """The median line across books - just a summary number for the list view."""
    points = sorted(b['line'] for b in books if b.get('line') is not None)
    if not points:
        return None
    mid = len(points) // 2
    return points[mid] if len(points) % 2 else (points[mid - 1] + points[mid]) / 2


def board(event_id: str, stat: str) -> dict:
    """Every player's line for one stat in one game.

    This is the browsing view: a plain list of what the books are offering, so
    a user can scan it, pick something that looks interesting to them, and go
    read the history behind it.
    """
    if not is_configured():
        return {
            'status': 'not_configured',
            'message': 'Live odds need an ODDS_API_KEY. Get a free key at the-odds-api.com.',
            'entries': [],
        }

    market = MARKET_BY_STAT.get(stat)
    if market is None:
        return {'status': 'no_market', 'message': f'No sportsbook market for {stat}.', 'entries': []}

    try:
        payload, remaining, fetched_at = _fetch_market(event_id, market)
    except Conserving:
        return {'status': 'conserving', 'message': CONSERVING_MESSAGE, 'entries': []}
    except urllib.error.HTTPError as exc:
        logger.warning("Odds API HTTP %s for event %s / %s", exc.code, event_id, market)
        return {'status': 'error', 'message': _http_message(exc), 'entries': []}
    except Exception as exc:  # noqa: BLE001 - odds are a nice-to-have, never fatal
        logger.warning("Odds board failed for %s/%s: %s", event_id, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'entries': []}

    by_player = _collect_players(payload, market)
    if not by_player:
        return {
            'status': 'no_market',
            'message': f'No {stat.replace("_", " ")} lines posted for this game yet. '
                       'Player props usually appear within a day or two of kickoff.',
            'entries': [],
        }

    entries = [
        {
            'player': name,
            'consensus_line': _consensus_line(books),
            'books': sorted(books, key=lambda b: b['book']),
        }
        for name, books in by_player.items()
    ]
    # Highest lines first: that is usually the workload order (a team's WR1
    # above its WR3), which is the most natural way to scan a game.
    entries.sort(key=lambda e: (e['consensus_line'] is None, -(e['consensus_line'] or 0), e['player']))

    return {
        'status': 'ok',
        'entries': entries,
        'game': {
            'id': event_id,
            'home_team': payload.get('home_team'),
            'away_team': payload.get('away_team'),
            'commence_time': payload.get('commence_time'),
        },
        'market': market,
        'stat': stat,
        'requests_remaining': remaining,
        'fetched_at': datetime.fromtimestamp(fetched_at, timezone.utc)
                      .isoformat(timespec='seconds'),
    }


def player_prop(player: str, team: str, opponent: str, stat: str,
                essential: bool = False) -> dict:
    """The lines for one player, for the panel on their analysis page.

    Served from the same cached event response the board uses, so opening a
    player after browsing the board costs nothing extra.
    """
    if not is_configured():
        return {
            'status': 'not_configured',
            'message': 'Live odds need an ODDS_API_KEY. Get a free key at the-odds-api.com.',
            'books': [],
        }

    market = MARKET_BY_STAT.get(stat)
    if market is None:
        return {'status': 'no_market', 'message': f'No sportsbook market for {stat}.', 'books': []}

    try:
        event = _find_event(team, opponent)
        if event is None:
            return {
                'status': 'no_event',
                'message': f'No upcoming {team} vs {opponent} game listed by the books.',
                'books': [],
            }
        payload, remaining, fetched_at = _fetch_market(
            event['id'], market, essential=essential,
        )
    except Conserving:
        return {'status': 'conserving', 'message': CONSERVING_MESSAGE, 'books': []}
    except urllib.error.HTTPError as exc:
        logger.warning("Odds API HTTP %s for %s/%s", exc.code, player, stat)
        return {'status': 'error', 'message': _http_message(exc), 'books': []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Odds lookup failed for %s/%s: %s", player, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'books': []}

    by_player = _collect_players(payload, market)
    wanted = normalize_player(player)
    books = next((v for k, v in by_player.items() if normalize_player(k) == wanted), [])

    if not books:
        return {
            'status': 'no_market',
            'message': f'No {stat.replace("_", " ")} line posted for {player} yet.',
            'books': [],
        }

    return {
        'status': 'ok',
        'books': sorted(books, key=lambda b: b['book']),
        'consensus_line': _consensus_line(books),
        # Carried so the caller can ask for this game's alternate ladder
        # without re-resolving the matchup to an event.
        'event_id': event['id'],
        'event': {
            'home_team': payload.get('home_team'),
            'away_team': payload.get('away_team'),
            'commence_time': payload.get('commence_time'),
        },
        'market': market,
        'requests_remaining': remaining,
        'fetched_at': datetime.fromtimestamp(fetched_at, timezone.utc)
                      .isoformat(timespec='seconds'),
        'books_count': len(books),
    }


def alternate_lines(event_id: str, stat: str, player: str,
                    essential: bool = False) -> dict:
    """The full ladder of lines and prices for one player and stat.

    Standard markets return a single line per book - the number the book
    expects to split action on. Alternate markets return the milestone ladder
    around it, so a receiver's 60.5 main line is accompanied by 40+, 50+, 70+
    and so on, each priced accordingly. That is what lets someone explore the
    trade-off between a softer line and a worse price.

    Costs one extra credit per game/stat on top of the main line, so callers
    should request it on demand rather than alongside the board.
    """
    if not is_configured():
        return {
            'status': 'not_configured',
            'message': 'Live odds need an ODDS_API_KEY. Get a free key at the-odds-api.com.',
            'lines': [],
        }

    market = ALTERNATE_MARKET_BY_STAT.get(stat)
    if market is None:
        return {
            'status': 'no_market',
            'message': f'The books do not publish alternate lines for {stat.replace("_", " ")}.',
            'lines': [],
        }

    try:
        payload, remaining, fetched_at = _fetch_market(
            event_id, market, essential=essential,
        )
    except Conserving:
        return {'status': 'conserving', 'message': CONSERVING_MESSAGE, 'lines': []}
    except urllib.error.HTTPError as exc:
        logger.warning("Alternate odds HTTP %s for %s/%s", exc.code, event_id, market)
        return {'status': 'error', 'message': _http_message(exc), 'lines': []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alternate odds failed for %s/%s: %s", event_id, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'lines': []}

    wanted = normalize_player(player)
    # line -> book -> prices. A book publishes many rows for one player here,
    # one per threshold, so they group by line rather than collapsing per book.
    by_line: dict[float, dict[str, dict]] = {}

    for bookmaker in payload.get('bookmakers', []):
        title = bookmaker.get('title', bookmaker.get('key'))
        for market_data in bookmaker.get('markets', []):
            if market_data.get('key') != market:
                continue
            for outcome in market_data.get('outcomes', []):
                if normalize_player(outcome.get('description')) != wanted:
                    continue
                point = outcome.get('point')
                side = (outcome.get('name') or '').lower()
                if point is None or side not in ('over', 'under'):
                    continue
                entry = by_line.setdefault(float(point), {}).setdefault(
                    title, {'book': title, 'over_price': None, 'under_price': None},
                )
                entry[f'{side}_price'] = outcome.get('price')

    if not by_line:
        return {
            'status': 'no_market',
            'message': f'No alternate {stat.replace("_", " ")} lines posted for {player} yet.',
            'lines': [],
        }

    lines = [
        {
            'line': point,
            'books': sorted(books.values(), key=lambda b: b['book']),
        }
        for point, books in sorted(by_line.items())
    ]

    return {
        'status': 'ok',
        'player': player,
        'stat': stat,
        'market': market,
        'lines': lines,
        'requests_remaining': remaining,
        'fetched_at': datetime.fromtimestamp(fetched_at, timezone.utc)
                      .isoformat(timespec='seconds'),
    }
