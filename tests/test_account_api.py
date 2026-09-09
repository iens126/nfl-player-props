"""The registration and recovery endpoints.

core/accounts.py owns the rules; these two functions own what happens when a
step fails halfway. That is where the interesting bugs live:

  * an auth user created but never given a profile squats a username forever,
    in a table nothing in this app can see;
  * a recovery endpoint that distinguishes "no such user" from "wrong code"
    becomes a way to enumerate who has an account;
  * a password successfully changed but reported as a failure sends the user
    away believing their old one still works.

Supabase is stubbed throughout — these are the handler's decisions, not the
provider's.
"""

import importlib
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.accounts import hash_recovery_code, new_recovery_code  # noqa: E402

register = importlib.import_module('api.account.register')
recover = importlib.import_module('api.account.recover')

USER_ID = '11111111-2222-3333-4444-555555555555'


def call(module, payload):
    """Drive a handler's do_POST without a socket, and return (status, body)."""
    handler = object.__new__(module.handler)
    raw = json.dumps(payload).encode()
    handler.headers = {'Content-Length': str(len(raw))}
    handler.rfile = BytesIO(raw)
    handler.wfile = BytesIO()
    captured = {}
    handler.send_response = lambda status: captured.__setitem__('status', status)
    handler.send_header = lambda key, value: None
    handler.end_headers = lambda: None

    module.handler.do_POST(handler)
    return captured['status'], json.loads(handler.wfile.getvalue())


@pytest.fixture
def api():
    """Stub Supabase for both endpoints; they share the module."""
    with mock.patch.object(register.supabase, 'configured', return_value=True):
        yield register.supabase


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegister:
    def test_creates_an_account_and_issues_a_recovery_code(self, api):
        profile = {'id': USER_ID, 'username': 'ferris', 'created_at': 'now'}
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'create_user', return_value=(200, {'id': USER_ID})) as create:
            rpc.side_effect = [(200, []), (200, [profile])]
            status, result = call(register, {'username': 'ferris', 'password': 'a' * 12})

        assert status == 201
        assert result['profile'] == profile
        assert result['recovery_code']

        # The address handed to the auth service is synthetic, not anything the
        # user typed — this is the guarantee the whole design rests on.
        assert create.call_args.args[0] == 'ferris@users.gridedge.invalid'

    def test_the_code_is_stored_only_as_a_hash(self, api):
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'create_user', return_value=(200, {'id': USER_ID})):
            rpc.side_effect = [(200, []), (200, [{'id': USER_ID, 'username': 'ferris'}])]
            _, result = call(register, {'username': 'ferris', 'password': 'a' * 12})

        stored = rpc.call_args_list[1].args[1]['p_code_hash']
        assert stored == hash_recovery_code(result['recovery_code'])
        assert result['recovery_code'] not in stored

    @pytest.mark.parametrize('payload', [
        {'username': 'ab', 'password': 'a' * 12},        # too short
        {'username': 'has space', 'password': 'a' * 12},
        {'username': 'ferris', 'password': 'short'},
        {'username': '', 'password': ''},
    ])
    def test_rejects_bad_input_before_touching_the_provider(self, api, payload):
        with mock.patch.object(api, 'create_user') as create:
            status, _ = call(register, payload)
        assert status == 400
        create.assert_not_called()

    def test_reports_a_taken_username_in_its_own_words(self, api):
        with mock.patch.object(api, 'rpc', return_value=(200, [{'id': USER_ID, 'username': 'ferris'}])), \
             mock.patch.object(api, 'create_user') as create:
            status, result = call(register, {'username': 'Ferris', 'password': 'a' * 12})

        assert status == 409
        assert result['message'] == 'That username is taken.'
        # No half-made auth user left behind by a name we knew was unavailable.
        create.assert_not_called()

    def test_rolls_back_the_auth_user_when_the_profile_fails(self, api):
        """Otherwise the name is held in auth.users by an account with no
        profile — invisible here, and unclaimable by the person who wanted it."""
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'create_user', return_value=(200, {'id': USER_ID})), \
             mock.patch.object(api, 'delete_user') as delete:
            rpc.side_effect = [(200, []), (409, {'code': '23505'})]
            status, result = call(register, {'username': 'ferris', 'password': 'a' * 12})

        assert status == 409
        assert result['message'] == 'That username is taken.'
        delete.assert_called_once_with(USER_ID)

    def test_rolls_back_on_an_unexpected_database_failure_too(self, api):
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'create_user', return_value=(200, {'id': USER_ID})), \
             mock.patch.object(api, 'delete_user') as delete:
            rpc.side_effect = [(200, []), (500, {'message': 'boom'})]
            status, _ = call(register, {'username': 'ferris', 'password': 'a' * 12})

        assert status == 502
        delete.assert_called_once_with(USER_ID)

    def test_says_so_when_accounts_are_not_configured(self):
        with mock.patch.object(register.supabase, 'configured', return_value=False):
            status, result = call(register, {'username': 'ferris', 'password': 'a' * 12})
        assert status == 503
        assert result['status'] == 'not_configured'


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

class TestRecover:
    def _account(self, code):
        return {'id': USER_ID, 'username': 'ferris', 'code_hash': hash_recovery_code(code)}

    def test_sets_a_new_password_and_issues_a_fresh_code(self, api):
        code = new_recovery_code()
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'set_password', return_value=(200, {})) as set_password:
            rpc.side_effect = [(200, [self._account(code)]), (204, {})]
            status, result = call(recover, {
                'username': 'ferris', 'recovery_code': code, 'password': 'b' * 12,
            })

        assert status == 200
        set_password.assert_called_once_with(USER_ID, 'b' * 12)
        assert result['recovery_code'] and result['recovery_code'] != code

    def test_the_replacement_code_is_what_gets_stored(self, api):
        code = new_recovery_code()
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'set_password', return_value=(200, {})):
            rpc.side_effect = [(200, [self._account(code)]), (204, {})]
            _, result = call(recover, {
                'username': 'ferris', 'recovery_code': code, 'password': 'b' * 12,
            })

        assert rpc.call_args_list[1].args[1]['p_code_hash'] == \
            hash_recovery_code(result['recovery_code'])

    def test_accepts_a_code_retyped_loosely(self, api):
        code = new_recovery_code()
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'set_password', return_value=(200, {})):
            rpc.side_effect = [(200, [self._account(code)]), (204, {})]
            status, _ = call(recover, {
                'username': ' Ferris ', 'recovery_code': code.lower().replace('-', ' '),
                'password': 'b' * 12,
            })
        assert status == 200

    def test_a_wrong_code_and_an_unknown_user_are_indistinguishable(self, api):
        """Telling them apart would make this an account-enumeration endpoint."""
        wrong_code = new_recovery_code()
        with mock.patch.object(api, 'rpc', return_value=(200, [self._account(new_recovery_code())])), \
             mock.patch.object(api, 'set_password') as set_password:
            bad_code = call(recover, {'username': 'ferris', 'recovery_code': wrong_code,
                                      'password': 'b' * 12})

        with mock.patch.object(api, 'rpc', return_value=(200, [])), \
             mock.patch.object(api, 'set_password'):
            no_user = call(recover, {'username': 'nobody', 'recovery_code': wrong_code,
                                     'password': 'b' * 12})

        assert bad_code == no_user
        assert bad_code[0] == 401
        set_password.assert_not_called()

    def test_an_account_with_no_recovery_row_cannot_be_opened(self, api):
        """A null hash must not be satisfiable by sending a null code."""
        with mock.patch.object(api, 'rpc', return_value=(200, [
            {'id': USER_ID, 'username': 'ferris', 'code_hash': None}
        ])), mock.patch.object(api, 'set_password') as set_password:
            status, _ = call(recover, {'username': 'ferris', 'recovery_code': 'X',
                                       'password': 'b' * 12})
        assert status == 401
        set_password.assert_not_called()

    def test_reports_the_truth_when_the_password_changed_but_the_code_did_not(self, api):
        """Saying "failed" here would send the user away trying their old
        password, which no longer works."""
        code = new_recovery_code()
        with mock.patch.object(api, 'rpc') as rpc, \
             mock.patch.object(api, 'set_password', return_value=(200, {})):
            rpc.side_effect = [(200, [self._account(code)]), (500, {'message': 'boom'})]
            status, result = call(recover, {
                'username': 'ferris', 'recovery_code': code, 'password': 'b' * 12,
            })

        assert status == 200
        assert result['status'] == 'partial'
        assert result['recovery_code'] is None
        assert 'was changed' in result['message']

    def test_rejects_a_new_password_that_is_too_short(self, api):
        with mock.patch.object(api, 'rpc') as rpc:
            status, _ = call(recover, {'username': 'ferris', 'recovery_code': 'X' * 20,
                                       'password': 'short'})
        assert status == 400
        rpc.assert_not_called()

    @pytest.mark.parametrize('payload', [
        {'recovery_code': 'X' * 20, 'password': 'b' * 12},
        {'username': 'ferris', 'password': 'b' * 12},
        {},
    ])
    def test_requires_a_username_and_a_code(self, api, payload):
        status, _ = call(recover, payload)
        assert status == 400
