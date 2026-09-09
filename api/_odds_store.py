"""Where odds snapshots and the credit count are kept between requests.

core/odds.py holds its cache in a module-level dict, which on a serverless
platform means most requests start with nothing and pay for a response the
service already had. This is the other half of that cache: a table two
processes can share, so a board a dozen people open costs one credit rather
than a dozen.

Failure here is never allowed to matter. Every method swallows its errors and
returns as though the store were empty, which puts core/odds.py back on the
behaviour it had before any of this existed — a wasted credit, not an outage.
"""

import urllib.parse
from datetime import datetime, timezone

from api import _supabase as supabase

SNAPSHOTS = 'odds_snapshots'
BUDGET = 'odds_budget'


def _epoch(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError):
        return None


class SupabaseStore:
    """The snapshot store backed by the project's Postgres."""

    def get(self, key: str):
        """(fetched_at, value) for a key, or None if it isn't there."""
        try:
            rows = supabase.select(
                SNAPSHOTS,
                f'key=eq.{urllib.parse.quote(key, safe="")}&select=payload,fetched_at&limit=1',
            )
        except Exception:  # noqa: BLE001
            return None
        if not rows:
            return None
        when = _epoch(rows[0].get('fetched_at'))
        payload = rows[0].get('payload') or {}
        if when is None or 'value' not in payload:
            return None
        return when, payload['value']

    def put(self, key: str, value, fetched_at: float) -> None:
        # Wrapped in an object rather than stored bare: the cached value is a
        # (payload, remaining) pair, and a top-level JSON array would come back
        # as a list of two things with nothing saying what they are.
        supabase.upsert(SNAPSHOTS, {
            'key': key,
            'payload': {'value': value},
            'fetched_at': datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
        }, on_conflict='key')

    def remaining(self) -> int | None:
        try:
            rows = supabase.select(BUDGET, 'id=eq.1&select=remaining&limit=1')
        except Exception:  # noqa: BLE001
            return None
        if not rows or rows[0].get('remaining') is None:
            return None
        try:
            return int(rows[0]['remaining'])
        except (TypeError, ValueError):
            return None

    def record_remaining(self, value: int) -> None:
        supabase.upsert(BUDGET, {
            'id': 1,
            'remaining': int(value),
            'seen_at': datetime.now(timezone.utc).isoformat(),
        }, on_conflict='id')


_installed = False


def install() -> None:
    """Point core/odds.py at this store, once, if there is a project to use.

    Called by the handlers rather than on import, so that importing the odds
    module at build time — scripts/precompute.py does — never reaches for a
    database it has no reason to need.
    """
    global _installed
    if _installed or not supabase.configured():
        return
    from core import odds
    odds.set_store(SupabaseStore())
    _installed = True
