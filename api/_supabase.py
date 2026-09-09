"""Minimal Supabase client for the serverless functions.

Standard library only, in keeping with api/requirements.txt: this is two HTTP
calls, and pulling in a client library for them would be the largest dependency
in the deployment.

Tokens are verified by asking Supabase who the bearer is rather than checking
the signature here. That costs one round trip on a request that already makes
several, and it buys a great deal: it works whatever algorithm the project
signs with, it needs no JWT secret in this environment, and a token that has
been revoked stops working immediately instead of at expiry.
"""

import json
import os
import urllib.error
import urllib.request

TIMEOUT = 10

URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
ANON_KEY = os.environ.get('SUPABASE_ANON_KEY') or ''
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or ''


def configured() -> bool:
    """Accounts are optional. Without these three the app runs as it always did."""
    return bool(URL and ANON_KEY and SERVICE_KEY)


def _post(path: str, payload: dict, key: str, token: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        f'{URL}{path}',
        data=json.dumps(payload).encode(),
        headers={
            'apikey': key,
            'Authorization': f'Bearer {token or key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode() or '{}'
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or '{}'
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {'message': raw}


def current_user(bearer: str | None) -> dict | None:
    """Resolve an access token to its user, or None if it isn't valid."""
    if not bearer:
        return None
    token = bearer[7:].strip() if bearer.lower().startswith('bearer ') else bearer.strip()
    if not token:
        return None

    request = urllib.request.Request(
        f'{URL}/auth/v1/user',
        headers={'apikey': ANON_KEY, 'Authorization': f'Bearer {token}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            user = json.loads(response.read().decode())
            return user if user.get('id') else None
    except urllib.error.HTTPError:
        return None
    except Exception:  # noqa: BLE001 - an unreachable auth server is a 401 to the caller
        return None


def select(table: str, params: str = '') -> list[dict]:
    """Read a table or view with the service key. Used by the settlement job."""
    url = f'{URL}/rest/v1/{table}'
    if params:
        url = f'{url}?{params}'
    request = urllib.request.Request(url, headers={
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        rows = json.loads(response.read().decode() or '[]')
    return rows if isinstance(rows, list) else []


def rpc(name: str, payload: dict) -> tuple[int, dict]:
    """Call a Postgres function with the service key.

    The service key bypasses row-level security, which is precisely why the
    only functions it calls are the two that enforce the rules themselves.
    """
    return _post(f'/rest/v1/rpc/{name}', payload, SERVICE_KEY)


# ---------------------------------------------------------------------------
# Admin auth
#
# Accounts are created here rather than in the browser, with the service key,
# because the auth user and the profile row have to arrive together and the
# browser cannot be trusted to finish what it starts. See api/account/.
# ---------------------------------------------------------------------------

def _admin(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        f'{URL}{path}',
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode() or '{}'
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or '{}'
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {'message': raw}


def create_user(email: str, password: str) -> tuple[int, dict]:
    """Create a confirmed password account.

    email_confirm is true because the address is synthetic (core/accounts.py)
    and there is no inbox that could ever confirm it. Supabase must also have
    email confirmation switched off for the project, or sign-up through any
    other path would sit unconfirmed forever.
    """
    return _admin('POST', '/auth/v1/admin/users', {
        'email': email,
        'password': password,
        'email_confirm': True,
    })


def set_password(user_id: str, password: str) -> tuple[int, dict]:
    """Set a new password for an existing user. Used by the recovery flow."""
    return _admin('PUT', f'/auth/v1/admin/users/{user_id}', {'password': password})


def delete_user(user_id: str) -> tuple[int, dict]:
    """Remove an auth user.

    Only used to undo a half-made account: if the auth user is created and the
    profile insert then fails, leaving the user behind would squat the username
    in auth.users where nothing in this app can see or clean it up.
    """
    return _admin('DELETE', f'/auth/v1/admin/users/{user_id}', {})


def upsert(table: str, row: dict, on_conflict: str) -> tuple[int, object]:
    """Insert a row, replacing any that collides on `on_conflict`.

    PostgREST needs both the conflict target and the merge preference; without
    them a repeat write is a duplicate-key error rather than an update, which
    for a cache means every snapshot after the first is silently lost.
    """
    request = urllib.request.Request(
        f'{URL}/rest/v1/{table}?on_conflict={on_conflict}',
        data=json.dumps(row).encode(),
        headers={
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates,return=minimal',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, {}
    except urllib.error.HTTPError as exc:
        return exc.code, {'message': exc.read().decode() or ''}
