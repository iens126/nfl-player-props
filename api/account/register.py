"""POST /api/account/register — create an account from a username and a password.

Nothing else is asked for. No email address, no phone number, no third-party
profile: the record this leaves behind is a username, a bankroll's worth of
picks, and the date it started. See core/accounts.py for why the auth service
still ends up holding a synthetic address, and why that address can never
reach a person.

Registration is here rather than in the browser because two things have to
happen together — the auth user and the profile row — and a half-made account
is one the user cannot repair themselves. If the second step fails, this
function undoes the first.

The response carries the one-time recovery code. It is the only time it is
ever sent anywhere: only its hash is stored, so if the user loses it, nobody —
including whoever runs the database — can tell them what it was.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api._shared import NO_CACHE, body, respond
from api import _supabase as supabase


def _fail(handler, status, message, code='error'):
    respond(handler, {'status': code, 'message': message}, status, cache=NO_CACHE)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        from core.accounts import (
            AccountError, hash_recovery_code, new_recovery_code, synthetic_email,
            validate_password, validate_username,
        )

        if not supabase.configured():
            _fail(self, 503, 'Accounts are not configured on this deployment.', 'not_configured')
            return

        payload = body(self)
        try:
            username = validate_username(payload.get('username'))
            password = validate_password(payload.get('password'))
        except AccountError as exc:
            _fail(self, 400, exc.message, exc.code)
            return

        # Checked before creating anything, purely so the user gets "that name
        # is taken" instead of the auth service's phrasing about an address
        # they never typed. The unique index is what actually enforces it.
        status, existing = supabase.rpc('account_by_username', {'p_username': username})
        if status < 400 and isinstance(existing, list) and existing:
            _fail(self, 409, 'That username is taken.', 'username')
            return

        status, user = supabase.create_user(synthetic_email(username), password)
        if status >= 400:
            message = str(user.get('msg') or user.get('message') or '')
            if 'already' in message.lower() or status in (409, 422):
                _fail(self, 409, 'That username is taken.', 'username')
                return
            _fail(self, 502, 'The account could not be created. Try again in a moment.')
            return

        user_id = user.get('id')
        if not user_id:
            _fail(self, 502, 'The account could not be created. Try again in a moment.')
            return

        code = new_recovery_code()
        status, result = supabase.rpc('register_account', {
            'p_user': user_id,
            'p_username': username,
            'p_code_hash': hash_recovery_code(code),
        })

        if status >= 400:
            # Roll back, or the username is squatted in auth.users by an
            # account with no profile — invisible to this app and unusable by
            # the person who tried to claim it.
            supabase.delete_user(user_id)
            if result.get('code') == '23505':
                _fail(self, 409, 'That username is taken.', 'username')
                return
            _fail(self, 502, 'The account could not be created. Try again in a moment.')
            return

        profile = result[0] if isinstance(result, list) else result
        respond(self, {
            'status': 'ok',
            'profile': profile,
            # Shown once, by the browser, and never retrievable again.
            'recovery_code': code,
        }, 201, cache=NO_CACHE)
