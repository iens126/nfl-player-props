"""The identity rules: usernames, passwords, synthetic addresses, recovery codes.

The property worth guarding hardest is the one the whole design rests on —
that nothing here can produce an address which reaches a real person.
"""

import pytest

from core.accounts import (
    AccountError, CODE_ALPHABET, EMAIL_DOMAIN, MIN_PASSWORD, canonical_code,
    hash_recovery_code, is_synthetic, new_recovery_code, normalize_username,
    recovery_code_matches, synthetic_email, username_from_email,
    validate_password, validate_username,
)


class TestUsernames:
    @pytest.mark.parametrize('name', ['abc', 'gridiron_ghost', 'x' * 20,
                                      '0start', 'Mixed_Case_99', 'a_b'])
    def test_accepts_valid(self, name):
        assert validate_username(name) == name

    @pytest.mark.parametrize('name', [
        '',  '  ', 'ab',            # too short
        'x' * 21,                   # too long
        '_leading',                 # must start alphanumeric
        'has space', 'has-dash', 'has.dot', 'has@at', 'émile',
        None,
    ])
    def test_rejects_invalid(self, name):
        with pytest.raises(AccountError):
            validate_username(name)

    def test_trims_surrounding_whitespace(self):
        assert validate_username('  ferris  ') == 'ferris'

    def test_normalize_is_case_folding(self):
        assert normalize_username('  Ferris ') == 'ferris'
        assert normalize_username(None) == ''


class TestPasswords:
    def test_accepts_long_enough(self):
        password = 'a' * MIN_PASSWORD
        assert validate_password(password) == password

    @pytest.mark.parametrize('password', ['', None, 'short', 'a' * (MIN_PASSWORD - 1)])
    def test_rejects_too_short(self, password):
        with pytest.raises(AccountError):
            validate_password(password)

    def test_rejects_absurdly_long(self):
        with pytest.raises(AccountError):
            validate_password('a' * 5000)

    def test_does_not_trim(self):
        """Leading and trailing spaces are part of a password, not decoration."""
        password = '  ' + 'a' * MIN_PASSWORD + '  '
        assert validate_password(password) == password


class TestSyntheticEmail:
    def test_built_from_the_username(self):
        assert synthetic_email('gridiron_ghost') == f'gridiron_ghost@{EMAIL_DOMAIN}'

    def test_is_case_insensitive(self):
        """Or "Ferris" and "ferris" become two accounts at the auth layer even
        though profiles_username_lower_idx says they are one."""
        assert synthetic_email('Ferris') == synthetic_email('ferris')

    def test_domain_can_never_resolve(self):
        """RFC 2606 reserves .invalid. This is the guarantee that no bug in
        this app can turn a username into mail sent to a real person."""
        assert EMAIL_DOMAIN.endswith('.invalid')

    def test_round_trips_to_the_username(self):
        assert username_from_email(synthetic_email('Ferris')) == 'ferris'

    @pytest.mark.parametrize('address', [
        'someone@gmail.com', 'someone@example.org', '', None,
        f'someone@not{EMAIL_DOMAIN}',
    ])
    def test_recognises_foreign_addresses(self, address):
        assert not is_synthetic(address)
        assert username_from_email(address) is None

    def test_recognises_our_own(self):
        assert is_synthetic(synthetic_email('ferris'))


class TestRecoveryCodes:
    def test_shape_is_typeable(self):
        code = new_recovery_code()
        groups = code.split('-')
        assert len(groups) == 4
        assert all(len(g) == 5 for g in groups)

    def test_avoids_ambiguous_characters(self):
        """0/O and 1/I/L are where a code copied off paper goes wrong."""
        for banned in '01OIL':
            assert banned not in CODE_ALPHABET
        assert set(canonical_code(new_recovery_code())) <= set(CODE_ALPHABET)

    def test_codes_are_unique(self):
        assert len({new_recovery_code() for _ in range(500)}) == 500

    def test_hash_does_not_contain_the_code(self):
        code = new_recovery_code()
        assert canonical_code(code) not in hash_recovery_code(code)

    def test_matches_its_own_hash(self):
        code = new_recovery_code()
        assert recovery_code_matches(code, hash_recovery_code(code))

    def test_tolerates_how_people_retype_it(self):
        code = new_recovery_code()
        stored = hash_recovery_code(code)
        for variant in (code.lower(), code.replace('-', ''), f'  {code}  ',
                        code.replace('-', ' ')):
            assert recovery_code_matches(variant, stored)

    def test_rejects_a_different_code(self):
        assert not recovery_code_matches(new_recovery_code(),
                                         hash_recovery_code(new_recovery_code()))

    @pytest.mark.parametrize('code,stored', [
        (None, 'abc'), ('abc', None), ('', ''), (None, None),
    ])
    def test_rejects_missing_inputs(self, code, stored):
        """An account with no recovery row must not be openable by sending
        nothing at all."""
        assert not recovery_code_matches(code, stored)
