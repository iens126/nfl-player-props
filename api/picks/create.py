"""POST /api/picks/create — the only way a ranked pick gets written.

Local picks (frontend/src/lib/picks.ts) let a user type any line at any price,
which is harmless while the bankroll is private. Once picks are ranked against
other people those two fields are the entire attack surface: "over 0.5
receiving yards at +2000" wins every week and tops the ROI board forever.

So this function, not the browser and not the database, is the trust boundary.
It checks four things, in this order, and writes nothing unless all four hold:

  1. the caller is who their token says they are;
  2. a real sportsbook is posting that exact player, stat, line and side —
     and the price comes from that board, not from the request;
  3. the game has not started, by the odds provider's clock, not the browser's;
  4. the user has the coins, checked and spent inside one transaction so two
     requests arriving together cannot both spend the same bankroll.

Steps 2 and 3 read one response, so the price and the deadline can never
disagree. Step 4 lives in place_pick() because only a transaction can do it.
"""

import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api._shared import NO_CACHE, body, respond
from api import _supabase as supabase

# What a raised exception in place_pick() should look like to a person.
DB_ERRORS = {
    'PICK_LOCKED': (409, 'That game has already kicked off — picks lock at kickoff.'),
    'STAKE_TOO_SMALL': (400, 'The smallest stake is 1 coin.'),
    'NO_PROFILE': (403, 'Pick a username before making picks.'),
}

REQUIRED = ('player', 'team', 'opponent', 'stat', 'side', 'line', 'stake')


def _fail(handler, status, message, code='error'):
    respond(handler, {'status': code, 'message': message}, status, cache=NO_CACHE)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        from core.wagers import WagerError, quote
        from api import _odds_store

        _odds_store.install()

        if not supabase.configured():
            _fail(self, 503, 'Accounts are not configured on this deployment.', 'not_configured')
            return

        user = supabase.current_user(self.headers.get('Authorization'))
        if user is None:
            _fail(self, 401, 'Sign in to make a ranked pick.', 'unauthorized')
            return

        payload = body(self)
        absent = [f for f in REQUIRED if payload.get(f) in (None, '')]
        if absent:
            _fail(self, 400, f'Missing: {", ".join(absent)}.')
            return

        try:
            line = float(payload['line'])
            stake = round(float(payload['stake']), 2)
        except (TypeError, ValueError):
            _fail(self, 400, 'Line and stake must be numbers.')
            return

        if stake < 1:
            _fail(self, 400, 'The smallest stake is 1 coin.')
            return

        # The price is deliberately not read from the request. Whatever the
        # client believes it is taking, the pick settles at what the board says.
        try:
            priced = quote(
                player=str(payload['player']),
                team=str(payload['team']),
                opponent=str(payload['opponent']),
                stat=str(payload['stat']),
                side=str(payload['side']),
                line=line,
            )
        except WagerError as exc:
            _fail(self, 422, exc.message, exc.code)
            return

        kickoff = priced.get('commence_time')
        if not kickoff:
            _fail(self, 422, 'The books have not published a kickoff time for that game yet.')
            return

        # Checked here as well as in place_pick(). This one produces the message
        # the user reads; the one in the database is what makes it true.
        when = datetime.fromisoformat(str(kickoff).replace('Z', '+00:00'))
        if when <= datetime.now(timezone.utc):
            _fail(self, 409, 'That game has already kicked off — picks lock at kickoff.', 'locked')
            return

        # Derived, not accepted: the NFL season a January game belongs to is
        # the previous calendar year, and a client that gets this wrong (or
        # lies about it) would have its pick settled against another season.
        season = when.year - 1 if when.month < 3 else when.year
        model_prob = payload.get('model_prob')

        status, result = supabase.rpc('place_pick', {
            'p_user': user['id'],
            'p_player': str(payload['player']),
            'p_team': str(payload['team']),
            'p_opponent': str(payload['opponent']),
            'p_stat': str(payload['stat']),
            'p_line': line,
            'p_side': priced['side'],
            'p_stake': stake,
            'p_price': priced['price'],
            'p_book': priced['book'],
            'p_event_id': priced['event_id'],
            'p_season': season,
            'p_kickoff': kickoff,
            'p_model_prob': float(model_prob) if model_prob is not None else None,
        })

        if status >= 400:
            message = str(result.get('message', ''))
            for key, (code, text) in DB_ERRORS.items():
                if message.startswith(key):
                    _fail(self, code, text, 'rejected')
                    return
            if message.startswith('INSUFFICIENT_FUNDS'):
                left = message.split(':', 1)[1] if ':' in message else '0'
                _fail(self, 409, f'Not enough coins — you have {left} available.', 'insufficient')
                return
            if result.get('code') == '23505':
                _fail(self, 409, 'You have already taken that exact line.', 'duplicate')
                return
            _fail(self, 502, 'The pick could not be saved. Try again in a moment.')
            return

        # PostgREST returns a single-row function result as the row itself.
        pick = result[0] if isinstance(result, list) else result
        respond(self, {'status': 'ok', 'pick': pick, 'quote': priced}, 201, cache=NO_CACHE)
