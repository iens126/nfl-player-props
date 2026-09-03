"""GET /api/odds/alternates — the full line/price ladder for one player.

Costs an extra API credit per game+stat, so the UI only calls this when a user
explicitly opens the ladder rather than as part of loading the board.
"""

from http.server import BaseHTTPRequestHandler

from api._shared import query, respond


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from core import odds as odds_api

        params = query(self)
        event_id, stat, player = params.get('event_id'), params.get('stat'), params.get('player')
        if not event_id or not stat or not player:
            respond(self, {
                'status': 'error',
                'message': 'Missing event_id, stat or player',
                'lines': [],
            }, 400)
            return

        respond(self, odds_api.alternate_lines(event_id, stat, player))
