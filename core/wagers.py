"""Rules for account-backed picks: what a pick may be, and what it paid.

This module is the trust boundary for the leaderboard. Local picks
(frontend/src/lib/picks.ts) let a user type any line and any price, which is
fine when the bankroll is private — but the moment picks are ranked against
other people, those two fields become the whole attack surface. Nothing in the
database can tell whether a book really offered "over 0.5 receiving yards at
+2000", so the check has to happen here, against the live board, before a pick
is ever written.

Two pieces, deliberately separate:

  quote()  — validates a proposed pick against what the books are actually
             offering and returns the price the user gets. The client's price
             is never trusted; it isn't even read.
  grade()  — settles a pick against the player's real stat line.

grade() is a line-for-line twin of gradePick() in picks.ts. They are pinned to
a shared specification (tests/fixtures/grading.json) that both test suites read,
so the two cannot drift apart unnoticed.
"""

from __future__ import annotations

from core import odds as odds_api

# Every account opens with the same bankroll. Coins are imaginary: nothing is
# purchasable, nothing cashes out, and the figure resets with the season.
STARTING_BANKROLL = 100.0

# A stake below a coin makes the ROI board gameable — a 0.01-coin flier on a
# longshot is a free option on first place — and rounds badly besides.
MIN_STAKE = 1.0

# ROI is profit over coins staked, so a single tiny winning longshot would
# otherwise sit at the top of the board all season having risked nothing. The
# floor is on coins staked rather than picks made, which is the distinction
# that matters: one genuinely large bet still qualifies, which is the point of
# having an ROI board at all.
ROI_QUALIFYING_STAKE = 25.0


class WagerError(Exception):
    """A pick that must not be written, with a message meant for the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def profit_for(stake: float, american_price: int | float) -> float:
    """Coins won on a winning bet at American odds."""
    price = float(american_price)
    if price == 0:
        return 0.0
    if price > 0:
        return stake * (price / 100.0)
    return stake * (100.0 / abs(price))


def implied_probability(price: int | float) -> float | None:
    """The probability a price implies, the book's margin included."""
    price = float(price)
    if price == 0:
        return None
    return -price / (-price + 100.0) if price < 0 else 100.0 / (price + 100.0)


# ---------------------------------------------------------------------------
# Validating a proposed pick against the live board
# ---------------------------------------------------------------------------

def _best_price(books: list[dict], side: str, line: float) -> tuple[int | None, str | None]:
    """The friendliest price any book is posting for exactly this side and line.

    Best-of-book rather than consensus, for two reasons: it is what a real
    bettor would take, and it is deterministic — averaging prices across books
    that post different lines produces a number nobody actually offered.
    """
    key = f'{side}_price'
    best: tuple[int, str] | None = None
    for entry in books:
        posted = entry.get('line')
        price = entry.get(key)
        if posted is None or price is None:
            continue
        if abs(float(posted) - line) > 1e-9:
            continue
        if best is None or int(price) > best[0]:
            best = (int(price), entry.get('book') or 'unknown')
    return best if best else (None, None)


def _lines_offering(books: list[dict], side: str) -> set[float]:
    """Every line this side actually has a price at.

    Collected so a refusal can name the nearest number a book will take,
    rather than leaving the user to guess which of the ladder's rungs exists.
    """
    key = f'{side}_price'
    return {
        float(entry['line'])
        for entry in books
        if entry.get('line') is not None and entry.get(key) is not None
    }


def quote(player: str, team: str, opponent: str, stat: str, side: str, line: float) -> dict:
    """Price a proposed pick, or explain why it can't be taken.

    Looks at the main line first and falls back to the alternate ladder, which
    is what makes "pick whatever line you want" true rather than a slogan: a
    receiver's 60.5 main line sits alongside 40+, 50+ and 70+, each with its
    own price. A line no book is posting is refused outright — that is the
    difference between a bold pick and an invented one.

    The kickoff time comes back from the same response, so the deadline and the
    price are read from one source and can't disagree.
    """
    if side not in ('over', 'under'):
        raise WagerError('bad_side', "A pick must be 'over' or 'under'.")

    # essential: a pick priced off a stale line is a bet the book is no
    # longer offering, which is the hole this whole module exists to close.
    main = odds_api.player_prop(player, team, opponent, stat, essential=True)
    if main['status'] != 'ok':
        raise WagerError(main['status'], main.get('message', 'No line available for that pick.'))

    event = main.get('event') or {}
    event_id = main.get('event_id')
    books = main.get('books', [])
    price, book = _best_price(books, side, line)
    source = 'main'
    offered = _lines_offering(books, side)

    if price is None:
        ladder = odds_api.alternate_lines(event_id, stat, player, essential=True)
        if ladder['status'] == 'ok':
            # Every rung is walked rather than stopping at the match, because
            # the refusal below is far more useful when it can name the nearest
            # number that does exist — and the ladder has already been paid for
            # by this point, so the extra pass is free.
            for rung in ladder.get('lines', []):
                rung_books = [{**b, 'line': rung['line']} for b in rung.get('books', [])]
                offered |= _lines_offering(rung_books, side)
                if abs(float(rung['line']) - line) < 1e-9:
                    price, book = _best_price(rung_books, side, line)
                    source = 'alternate'

    if price is None:
        pretty = stat.replace('_', ' ')
        message = f'No book is posting {player} {side} {line:g} {pretty} right now.'
        if offered:
            # Ties go to the lower line, which is the friendlier one to be sent
            # towards on an over and the honest one on an under.
            nearest = min(offered, key=lambda candidate: (abs(candidate - line), candidate))
            message += f' The closest {side} line on offer is {nearest:g}.'
        else:
            message += ' Pick a line that appears on the board or in the alternate ladder.'
        raise WagerError('no_line', message)

    return {
        'price': price,
        'book': book,
        'line': line,
        'side': side,
        'source': source,
        'event_id': event_id,
        'commence_time': event.get('commence_time'),
        'home_team': event.get('home_team'),
        'away_team': event.get('away_team'),
    }


# ---------------------------------------------------------------------------
# Settling
# ---------------------------------------------------------------------------

def grade(side: str, line: float, actual: float | None) -> str:
    """hit / miss / void for one pick. The twin of gradePick() in picks.ts.

    A missing stat line voids rather than losing: a player who was inactive or
    never suited up never had a chance to clear the number, and a sportsbook
    would refund the ticket rather than keep the stake.
    """
    if actual is None:
        return 'void'
    return 'hit' if (actual >= line if side == 'over' else actual < line) else 'miss'


def settle(side: str, line: float, stake: float, price: int | float,
           actual: float | None) -> dict:
    """Status and profit together, which is all a settlement row holds."""
    status = grade(side, line, actual)
    if status == 'hit':
        profit = profit_for(stake, price)
    elif status == 'miss':
        profit = -stake
    else:
        profit = 0.0
    return {'status': status, 'actual': actual, 'profit': round(profit, 2)}
