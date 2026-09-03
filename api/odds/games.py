"""GET /api/odds/games — games the books have listed."""

from http.server import BaseHTTPRequestHandler

from api._shared import respond


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from core import odds as odds_api
        respond(self, odds_api.upcoming_games())
