"""POST /api/account/recover — set a new password using a recovery code.

This is the entire account-recovery story, and it exists because the sign-up
flow deliberately collects no way to contact anybody. There is no reset link,
because there is no address to send one to; there is a code the user was shown
once and told to keep.

The trade is stated plainly rather than hidden: an account whose password and
recovery code are both lost is gone, and no amount of asking can bring it
back, because the server genuinely does not know who owns it.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api._shared import NO_CACHE, body, respond
from api import _supabase as supabase

# One message for "no such user" and for "wrong code" alike. Telling them apart
# would turn this endpoint into a way to enumerate who has an account, and the
# usernames on the leaderboard are public enough already.
REJECTED = 'That username and recovery code do not match.'


def _fail(handler, status, message, code='error'):
    respond(handler, {'status': code, 'message': message}, status, cache=NO_CACHE)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        from core.accounts import (
            AccountError, hash_recovery_code, new_recovery_code,
            recovery_code_matches, validate_password,
        )

        if not supabase.configured():
            _fail(self, 503, 'Accounts are not configured on this deployment.', 'not_configured')
            return

        payload = body(self)
        username = str(payload.get('username') or '').strip()
        supplied = str(payload.get('recovery_code') or '').strip()
        if not username or not supplied:
            _fail(self, 400, 'Enter your username and your recovery code.')
            return

        try:
            password = validate_password(payload.get('password'))
        except AccountError as exc:
            _fail(self, 400, exc.message, exc.code)
            return

        status, rows = supabase.rpc('account_by_username', {'p_username': username})
        if status >= 400:
            _fail(self, 502, 'Could not check that just now. Try again in a moment.')
            return

        account = rows[0] if isinstance(rows, list) and rows else None
        if not account or not recovery_code_matches(supplied, account.get('code_hash')):
            _fail(self, 401, REJECTED, 'rejected')
            return

        status, _ = supabase.set_password(str(account['id']), password)
        if status >= 400:
            _fail(self, 502, 'The password could not be changed. Try again in a moment.')
            return

        # The spent code is replaced rather than deleted: finishing a recovery
        # should not leave the account with no way back in next time.
        replacement = new_recovery_code()
        status, _ = supabase.rpc('rotate_recovery', {
            'p_user': str(account['id']),
            'p_code_hash': hash_recovery_code(replacement),
        })
        if status >= 400:
            # The password did change, so saying "it failed" would be a lie
            # that stops them trying their new one. Say what is actually true.
            respond(self, {
                'status': 'partial',
                'username': account.get('username'),
                'recovery_code': None,
                'message': 'Your password was changed, but a new recovery code could not be '
                           'issued. Sign in and try recovery again to get one.',
            }, 200, cache=NO_CACHE)
            return

        respond(self, {
            'status': 'ok',
            'username': account.get('username'),
            'recovery_code': replacement,
        }, 200, cache=NO_CACHE)
