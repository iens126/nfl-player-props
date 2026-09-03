"""GET /api/odds/board — every player's line for one stat in one game."""

from http.server import BaseHTTPRequestHandler

from api._shared import query, respond


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from core import odds as odds_api

        params = query(self)
        event_id, stat = params.get('event_id'), params.get('stat')
        if not event_id or not stat:
            respond(self, {'status': 'error', 'message': 'Missing event_id or stat', 'entries': []}, 400)
            return

        board = odds_api.board(event_id, stat)
        # The board is tagged with team/opponent by the frontend from its own
        # static index, so this function stays free of pandas and nflverse.
        respond(self, board)
