"""GET /api/odds — the lines for one player and stat."""

from http.server import BaseHTTPRequestHandler

from api._shared import query, respond


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from core import odds as odds_api

        params = query(self)
        required = ['player', 'team', 'opponent', 'stat']
        absent = [name for name in required if not params.get(name)]
        if absent:
            respond(self, {'status': 'error', 'message': f"Missing: {', '.join(absent)}", 'books': []}, 400)
            return

        respond(self, odds_api.player_prop(
            params['player'], params['team'].upper(), params['opponent'].upper(), params['stat'],
        ))
