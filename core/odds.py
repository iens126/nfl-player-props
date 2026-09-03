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


def abbr_for_team_name(name: str | None) -> str | None:
    """nflverse abbreviation for a full team name, or None if unrecognised."""
    if not name:
        return None
    return ABBR_BY_TEAM_NAME.get(name.strip())


_cache: dict[str, tuple[float, object]] = {}


def api_key() -> str | None:
    key = os.environ.get(ODDS_API_KEY_ENV, "").strip()
    return key or None


def is_configured() -> bool:
    return api_key() is not None


def _cached(key: str, loader):
    entry = _cache.get(key)
    now = time.time()
    if entry is not None and (now - entry[0]) < CACHE_MINUTES * 60:
        return entry[1]
    value = loader()
    _cache[key] = (now, value)
    return value


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
        return payload, remaining


def list_events():
    """Upcoming NFL events, so a matchup can be resolved to an event id."""
    def _load():
        events, _ = _get(f"/sports/{SPORT}/events", {})
        return events
    return _cached("events", _load)


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


def _http_message(exc: urllib.error.HTTPError) -> str:
    if exc.code in (401, 403):
        return 'Invalid or expired API key.'
    if exc.code == 429:
        return 'Odds API quota exhausted for this billing period.'
    return f'Odds API error ({exc.code}).'


def _fetch_market(event_id: str, market: str):
    """One event's prices for one market. This is the billed call - 1 credit."""
    def _load():
        return _get(
            f"/sports/{SPORT}/events/{event_id}/odds",
            {'regions': 'us', 'markets': market, 'oddsFormat': 'american',
             'bookmakers': DEFAULT_BOOKMAKERS},
        )
    return _cached(f"props:{event_id}:{market}", _load)


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
        payload, remaining = _fetch_market(event_id, market)
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
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def player_prop(player: str, team: str, opponent: str, stat: str) -> dict:
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
        payload, remaining = _fetch_market(event['id'], market)
    except urllib.error.HTTPError as exc:
        logger.warning("Odds API HTTP %s for %s/%s", exc.code, player, stat)
        return {'status': 'error', 'message': _http_message(exc), 'books': []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Odds lookup failed for %s/%s: %s", player, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'books': []}

    by_player = _collect_players(payload, market)
    books = next(
        (v for k, v in by_player.items() if k.strip().lower() == player.strip().lower()),
        [],
    )

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
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'books_count': len(books),
    }


def alternate_lines(event_id: str, stat: str, player: str) -> dict:
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
        payload, remaining = _fetch_market(event_id, market)
    except urllib.error.HTTPError as exc:
        logger.warning("Alternate odds HTTP %s for %s/%s", exc.code, event_id, market)
        return {'status': 'error', 'message': _http_message(exc), 'lines': []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alternate odds failed for %s/%s: %s", event_id, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'lines': []}

    wanted = player.strip().lower()
    # line -> book -> prices. A book publishes many rows for one player here,
    # one per threshold, so they group by line rather than collapsing per book.
    by_line: dict[float, dict[str, dict]] = {}

    for bookmaker in payload.get('bookmakers', []):
        title = bookmaker.get('title', bookmaker.get('key'))
        for market_data in bookmaker.get('markets', []):
            if market_data.get('key') != market:
                continue
            for outcome in market_data.get('outcomes', []):
                if (outcome.get('description') or '').strip().lower() != wanted:
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
            'best_over': _best_price(books.values(), 'over_price'),
            'best_under': _best_price(books.values(), 'under_price'),
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
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def _best_price(books, side: str):
    """The most favourable American price across books for one side.

    Higher is always better for the bettor: +150 pays more than +120, and -105
    costs less than -130. On that scale the largest number wins either way.
    """
    prices = [b[side] for b in books if b.get(side) is not None]
    return max(prices) if prices else None
