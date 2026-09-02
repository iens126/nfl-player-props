"""Live sportsbook lines from The Odds API, for comparison against the model.

The point of this is comparison, not tailing: a book's line is the market's
estimate of the same quantity the model estimates, so the interesting number is
the gap between them. That gap is what the API returns alongside the raw prices.

Requires an API key in ODDS_API_KEY (https://the-odds-api.com - the free tier
is 500 credits/month). With no key configured, every call here returns a result
that says so rather than raising, so the rest of the app keeps working and the
UI can explain what's missing.

Credit discipline matters: player props are billed per event *per market*, so a
handful of page loads can burn a month of free quota. Responses are therefore
cached for ODDS_CACHE_MINUTES (default 10) and only the single market the user
is actually looking at is ever requested.
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


def player_prop(player: str, team: str, opponent: str, stat: str) -> dict:
    """Live over/under lines for one player and stat across the major books.

    Returns a dict that always has a `status` field, so the caller can render
    the reason for an empty result rather than a blank panel:
    `ok`, `not_configured`, `no_market`, `no_event`, or `error`.
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

        def _load():
            return _get(
                f"/sports/{SPORT}/events/{event['id']}/odds",
                {'regions': 'us', 'markets': market, 'oddsFormat': 'american',
                 'bookmakers': DEFAULT_BOOKMAKERS},
            )

        payload, remaining = _cached(f"props:{event['id']}:{market}", _load)
    except urllib.error.HTTPError as exc:
        detail = 'Invalid or expired API key.' if exc.code in (401, 403) else (
            'Odds API quota exhausted.' if exc.code == 429 else f'Odds API error ({exc.code}).')
        logger.warning("Odds API HTTP %s for %s/%s", exc.code, player, stat)
        return {'status': 'error', 'message': detail, 'books': []}
    except Exception as exc:  # noqa: BLE001 - odds are a nice-to-have, never fatal
        logger.warning("Odds lookup failed for %s/%s: %s", player, stat, exc)
        return {'status': 'error', 'message': 'Could not reach the odds provider.', 'books': []}

    books = []
    for bookmaker in payload.get('bookmakers', []):
        for market_data in bookmaker.get('markets', []):
            if market_data.get('key') != market:
                continue
            over = under = None
            for outcome in market_data.get('outcomes', []):
                # Player props carry the player's name in `description`.
                if (outcome.get('description') or '').strip().lower() != player.strip().lower():
                    continue
                if (outcome.get('name') or '').lower() == 'over':
                    over = outcome
                elif (outcome.get('name') or '').lower() == 'under':
                    under = outcome
            if over is None and under is None:
                continue
            reference = over or under
            books.append({
                'book': bookmaker.get('title', bookmaker.get('key')),
                'line': reference.get('point'),
                'over_price': over.get('price') if over else None,
                'under_price': under.get('price') if under else None,
                'implied_over': _american_to_implied(over.get('price')) if over else None,
                'implied_under': _american_to_implied(under.get('price')) if under else None,
                'last_update': market_data.get('last_update'),
            })

    if not books:
        return {
            'status': 'no_market',
            'message': f'No {stat.replace("_", " ")} line posted for {player} yet.',
            'books': [],
        }

    return {
        'status': 'ok',
        'books': sorted(books, key=lambda b: b['book']),
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
