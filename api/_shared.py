"""Shared plumbing for the odds serverless functions.

Live odds are the one thing the static build can't do itself: they change by
the minute and need a secret API key, which cannot ship to a browser. So they
stay server-side — but as three tiny functions that only wake when someone
looks at odds, rather than an always-on service the whole app depends on.

These import core/odds.py directly, so the module stays under the Python test
suite rather than being reimplemented in JavaScript and drifting.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# vercel.json includes core/** alongside these functions.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def query(handler: BaseHTTPRequestHandler) -> dict:
    """Flatten the request's query string to single values."""
    raw = parse_qs(urlparse(handler.path).query)
    return {key: values[0] for key, values in raw.items() if values}


def respond(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(body)))
    # Odds are cached upstream for ODDS_CACHE_MINUTES; a short edge cache keeps
    # repeated page loads from spending API credits.
    handler.send_header('Cache-Control', 'public, max-age=60, stale-while-revalidate=300')
    handler.end_headers()
    handler.wfile.write(body)


def missing(handler: BaseHTTPRequestHandler, *names: str) -> list[str]:
    params = query(handler)
    return [n for n in names if not params.get(n)]
