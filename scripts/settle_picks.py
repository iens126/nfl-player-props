"""Settle account picks whose games have been played.

Runs as a step in the daily data refresh, right after the bundle is rebuilt and
checked. That ordering matters: the leaderboard is graded from the same JSON
the site serves, so a user can never see one result on their picks page and a
different one on the board.

This is the only process with permission to write a settlement, which is what
lets the browser be trusted with none of it.

Three things it has to get right:

  Which game.  A pick stores a kickoff, not a week — the client's idea of the
    week is not trusted, because a pick pointed at the wrong week settles
    against a game the player has already played. The week is resolved here,
    from the real schedule, by matching the two teams and the kickoff date.

  Didn't play vs hasn't been loaded yet.  Both look like "no row in the game
    log". nflverse takes a day or two to publish, so a pick stays pending until
    the grace window below has passed; only then does a missing stat line mean
    the player didn't record one, which voids the pick and returns the stake.

  Nothing else.  Profit is computed by settle_pick() in the database from the
    stake and price already on the ticket, so this job cannot pay out a number
    that disagrees with the pick it is settling. It reports what it observed:
    a status and the player's real figure.

Usage:
    python scripts/settle_picks.py [--bundle frontend/public/data] [--dry-run]

Needs SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_KEY. Exits quietly
if they are absent — accounts are optional, and a deployment without them still
refreshes its data.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import _supabase as supabase
from core.wagers import grade

# nflverse publishes a day or two behind kickoff. Until this much time has
# passed, a missing stat line means "not loaded yet" and the pick waits; after
# it, the player genuinely didn't record one and the pick voids. Sized so a
# Monday night game is settled by Wednesday's run rather than voided by
# Tuesday's, which would refund a pick that actually lost.
GRACE = timedelta(hours=48)

EASTERN = ZoneInfo('America/New_York')


def load_bundle(root: Path) -> tuple[dict[str, str], Path]:
    """Player name -> slug, from the same index the browser uses."""
    index = json.loads((root / 'index.json').read_text())
    return {p['name']: p['slug'] for p in index['players']}, root / 'players'


def game_log(players_dir: Path, slug: str) -> list[dict]:
    path = players_dir / f'{slug}.json'
    if not path.exists():
        return []
    return json.loads(path.read_text()).get('games', [])


def resolve_week(schedule, season: int, team: str, opponent: str, kickoff: datetime) -> int | None:
    """The week of the game these two teams played on the kickoff's date.

    Matched on the date in US Eastern, not UTC: an 8:20pm ET Sunday kickoff is
    already Monday in UTC, and a naive date comparison puts every night game on
    the wrong day.
    """
    day = kickoff.astimezone(EASTERN).date()
    pair = {team, opponent}
    for row in schedule:
        if row['season'] != season or {row['home_team'], row['away_team']} != pair:
            continue
        if row['gameday'] == day:
            return int(row['week'])
    # Kickoff can be moved after a pick is taken (flex scheduling, weather). The
    # matchup is unambiguous within a season, so fall back to it.
    for row in schedule:
        if row['season'] == season and {row['home_team'], row['away_team']} == pair:
            return int(row['week'])
    return None


def load_schedule(seasons: list[int]) -> list[dict]:
    import nflreadpy as nfl
    frame = nfl.load_schedules(seasons).to_pandas()
    frame = frame[['season', 'week', 'gameday', 'home_team', 'away_team']].dropna(
        subset=['home_team', 'away_team'],
    )
    frame['gameday'] = frame['gameday'].astype('datetime64[ns]')
    return [
        {
            'season': int(r.season), 'week': int(r.week), 'gameday': r.gameday.date(),
            'home_team': str(r.home_team), 'away_team': str(r.away_team),
        }
        for r in frame.itertuples()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', default='frontend/public/data', type=Path)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be settled without writing anything.')
    args = parser.parse_args()

    if not supabase.configured():
        print('Accounts are not configured (SUPABASE_* unset) — nothing to settle.')
        return 0

    pending = supabase.select('pending_settlement', 'order=kickoff.asc')
    if not pending:
        print('No picks are waiting on a result.')
        return 0

    slugs, players_dir = load_bundle(args.bundle)
    schedule = load_schedule(sorted({int(p['season']) for p in pending}))
    now = datetime.now(timezone.utc)

    settled = waiting = failed = 0
    for pick in pending:
        kickoff = datetime.fromisoformat(str(pick['kickoff']).replace('Z', '+00:00'))
        season = int(pick['season'])
        week = resolve_week(schedule, season, pick['team'], pick['opponent'], kickoff)

        actual = None
        if week is not None:
            row = next(
                (g for g in game_log(players_dir, slugs.get(pick['player'], ''))
                 if int(g.get('season', -1)) == season and int(g.get('week', -1)) == week),
                None,
            )
            if row is not None:
                value = row.get(pick['stat'])
                if isinstance(value, (int, float)):
                    actual = float(value)

        if actual is None and now - kickoff < GRACE:
            # The result may simply not have been published yet.
            waiting += 1
            continue

        status = grade(pick['side'], float(pick['line']), actual)
        label = (f"{pick['player']} {pick['side']} {pick['line']} {pick['stat']} "
                 f"-> {status}" + (f" ({actual:g})" if actual is not None else ' (no stat line)'))

        if args.dry_run:
            print(f'  would settle: {label}')
            settled += 1
            continue

        code, result = supabase.rpc('settle_pick', {
            'p_pick_id': pick['id'],
            'p_status': status,
            'p_actual': actual,
            'p_week': week,
        })
        if code >= 400:
            print(f'  FAILED: {label} — {result.get("message", code)}', file=sys.stderr)
            failed += 1
        else:
            print(f'  settled: {label}')
            settled += 1

    print(f'{settled} settled, {waiting} still waiting on results, {failed} failed.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
