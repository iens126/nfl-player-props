"""Prove a Supabase project is wired up correctly, end to end.

Runs the real registration and recovery handlers — the same code Vercel will
run — against a live project, then deletes everything it made. Nothing it
prints contains a key or a password.

Usage:
    python scripts/check_supabase.py .env.supabase

The env file is plain KEY=value lines:

    SUPABASE_URL=https://<ref>.supabase.co
    SUPABASE_ANON_KEY=sb_publishable_...
    SUPABASE_SERVICE_KEY=sb_secret_...
"""

import json
import os
import secrets
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT.parent))

REQUIRED = ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_KEY')

PASS, FAIL, INFO = '  PASS', '  FAIL', '   ->'


def load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def call(module, payload):
    """Drive a Vercel handler's do_POST without a socket."""
    handler = object.__new__(module.handler)
    raw = json.dumps(payload).encode()
    handler.headers = {'Content-Length': str(len(raw))}
    handler.rfile = BytesIO(raw)
    handler.wfile = BytesIO()
    captured = {}
    handler.send_response = lambda status: captured.__setitem__('status', status)
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None
    module.handler.do_POST(handler)
    return captured['status'], json.loads(handler.wfile.getvalue())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    env_file = Path(sys.argv[1]).expanduser()
    if not env_file.exists():
        print(f'No such env file: {env_file}')
        return 2
    load_env(env_file)

    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f'FAIL  env file is missing: {", ".join(missing)}')
        return 1

    # Imported only now: _supabase reads its configuration at import time.
    import importlib
    from api import _supabase as supabase
    register = importlib.import_module('api.account.register')
    recover = importlib.import_module('api.account.recover')

    ref = os.environ['SUPABASE_URL'].split('//', 1)[-1].split('.', 1)[0]
    print(f'Checking project {ref}\n')

    username = 'zzcheck' + secrets.token_hex(4)
    password = secrets.token_urlsafe(18)
    new_password = secrets.token_urlsafe(18)
    user_id = None
    failures = 0

    try:
        # 1. Can the publishable key read a table behind RLS?
        print('1. Publishable key reaches the REST API')
        try:
            supabase.select('profiles', 'select=id&limit=1')
            print(PASS)
        except Exception as exc:  # noqa: BLE001
            print(FAIL, f'{type(exc).__name__}: {exc}')
            if '401' in str(exc) or '403' in str(exc):
                print(INFO, 'The publishable key or the project URL is wrong.')
            elif '404' in str(exc):
                print(INFO, 'No `profiles` table — has supabase/schema.sql been run?')
            print(INFO, 'Nothing was created; fix and re-run.')
            failures += 1
            return 1

        # 2. Does the secret key reach a service-role-only function?
        print('2. Secret key can call a restricted database function')
        status, _ = supabase.rpc('account_by_username', {'p_username': username})
        if status < 400:
            print(PASS)
        else:
            print(FAIL, f'HTTP {status}')
            print(INFO, 'Either the schema has not been run, or the secret key is wrong.')
            failures += 1
            return 1

        # 3. The real registration handler.
        print('3. Registration creates an account')
        status, result = call(register, {'username': username, 'password': password})
        if status == 201 and result.get('recovery_code'):
            user_id = result['profile']['id']
            print(PASS, f'(username {username})')
        else:
            print(FAIL, f'HTTP {status}: {result.get("message")}')
            print(INFO, 'If this says the account could not be created, the secret key')
            print(INFO, 'may lack admin rights — try the Legacy service_role key.')
            return 1

        code = result['recovery_code']

        # 4. Did both rows land?
        print('4. Profile and recovery rows both exist')
        profiles = supabase.select('profiles', f'id=eq.{user_id}&select=id,username')
        recovery = supabase.select('recovery', f'user_id=eq.{user_id}&select=user_id')
        if profiles and recovery:
            print(PASS)
        else:
            print(FAIL, f'profiles={len(profiles)} recovery={len(recovery)}')
            failures += 1

        # 5. The recovery code actually works.
        print('5. Recovery code sets a new password')
        status, recovered = call(recover, {
            'username': username, 'recovery_code': code, 'password': new_password,
        })
        if status == 200 and recovered.get('recovery_code'):
            print(PASS, '(and a fresh code was issued)')
        else:
            print(FAIL, f'HTTP {status}: {recovered.get("message")}')
            failures += 1

        # 6. A wrong code must be refused.
        print('6. A wrong recovery code is refused')
        status, _ = call(recover, {
            'username': username, 'recovery_code': 'AAAAA-AAAAA-AAAAA-AAAAA',
            'password': new_password,
        })
        if status == 401:
            print(PASS)
        else:
            print(FAIL, f'expected HTTP 401, got {status}')
            failures += 1

    finally:
        if user_id:
            print('\nCleaning up the test account')
            status, _ = supabase.delete_user(user_id)
            left = supabase.select('profiles', f'id=eq.{user_id}&select=id')
            if status < 400 and not left:
                print(PASS, 'removed')
            else:
                print(FAIL, f'could not remove {username} — delete it in the dashboard')
                failures += 1

    print()
    if failures:
        print(f'{failures} check(s) failed.')
        return 1
    print('All checks passed. These keys work with this codebase.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
