"""Usernames, passwords and recovery codes — the whole identity model.

GridEdge asks for a username and a password. It does not ask for an email
address, a phone number, or anything else about the person typing, and it has
nowhere to put such a thing if they offered it: `profiles` is (id, username,
created_at) and that is the entire record of who somebody is.

The awkward part is that Supabase's auth service will not create a
password account without an identifier, and it only accepts an email address
or a phone number. So we synthesise one from the username:

    gridiron_ghost  ->  gridiron_ghost@users.gridedge.invalid

`.invalid` is reserved by RFC 2606 and can never resolve, which is the point:
this address is a primary key wearing a costume, and no bug, misconfiguration
or future change of provider can turn it into a message sent to a real person.
Email confirmation must be switched off on the Supabase project (Authentication
-> Providers -> Email -> "Confirm email"), because there is no inbox to confirm.

What follows from having no contact address is that a forgotten password
cannot be mailed back. That is not an oversight to be fixed later; it is the
direct cost of the requirement, and the only honest way to pay it is to hand
the user a recovery code at signup and tell them plainly that it is the only
way back in. Hence `new_recovery_code`.

Everything here is pure: no network, no database. The functions that talk to
Supabase live in api/account/, and they lean on this module so the rules are
tested without a project to test against.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

# The synthetic-address domain. Must match ACCOUNT_EMAIL_DOMAIN in
# frontend/src/lib/account.ts, which builds the same address to sign in with.
#
# Reserved by RFC 2606, so it is guaranteed never to resolve. Do not "fix" this
# to a domain that actually exists.
EMAIL_DOMAIN = 'users.gridedge.invalid'

# Same rule as the profiles_username_check constraint in supabase/schema.sql:
# start with a letter or digit, then letters, digits and underscores, 3-20 long.
USERNAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_]{2,19}$')

USERNAME_RULE = 'Usernames are 3–20 characters: letters, numbers and underscores, starting with a letter or number.'

# Longer than a site with a "forgot password" link would need. There is no
# such link here, but there is a recovery code, so this is a floor against
# guessing rather than a substitute for recovery.
MIN_PASSWORD = 10
MAX_PASSWORD = 200

PASSWORD_RULE = f'Passwords must be at least {MIN_PASSWORD} characters.'

# Crockford-style: no 0/O, no 1/I/L. Recovery codes get written down and typed
# back months later, and the pairs above are where that goes wrong.
CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTVWXYZ'
CODE_GROUPS = 4
CODE_GROUP_LEN = 5


class AccountError(Exception):
    """A rejection with a message worth showing the user."""

    def __init__(self, message: str, code: str = 'invalid'):
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_username(username: str | None) -> str:
    """Trim and casefold. Storage keeps the user's capitalisation; this is
    for the comparisons — matching profiles_username_lower_idx, which is what
    stops "Ferris" and "ferris" both existing and impersonating each other."""
    return (username or '').strip().lower()


def validate_username(username: str | None) -> str:
    """Return the username as typed, or raise with the reason it won't do."""
    candidate = (username or '').strip()
    if not candidate:
        raise AccountError('Choose a username.', 'username')
    if not USERNAME_RE.match(candidate):
        raise AccountError(USERNAME_RULE, 'username')
    return candidate


def validate_password(password: str | None) -> str:
    if not password:
        raise AccountError('Choose a password.', 'password')
    if len(password) < MIN_PASSWORD:
        raise AccountError(PASSWORD_RULE, 'password')
    # Supabase will reject an over-long password anyway; failing here gives a
    # better message than the provider's.
    if len(password) > MAX_PASSWORD:
        raise AccountError(f'Passwords must be under {MAX_PASSWORD} characters.', 'password')
    return password


def synthetic_email(username: str) -> str:
    """The address Supabase stores instead of a real one.

    Built from the lowercased username so the auth service's own uniqueness
    check agrees with profiles_username_lower_idx: two people cannot end up
    with the same name in different cases because one of the two layers was
    case-sensitive and the other wasn't.
    """
    return f'{normalize_username(username)}@{EMAIL_DOMAIN}'


def is_synthetic(email: str | None) -> bool:
    """Whether an address is one of ours — i.e. not a real contact address.

    Used to assert that nothing has quietly started storing real emails.
    """
    return bool(email) and str(email).strip().lower().endswith(f'@{EMAIL_DOMAIN}')


def username_from_email(email: str | None) -> str | None:
    """Recover the username from a synthetic address, or None if not ours."""
    if not is_synthetic(email):
        return None
    return str(email).strip().lower().split('@', 1)[0]


def new_recovery_code() -> str:
    """A fresh recovery code: 20 characters of ~98 bits, in typeable groups.

    This is the only way back into an account whose password is forgotten, so
    it is generated with secrets, shown exactly once, and stored only as a
    hash. Nobody — including whoever runs the database — can read it back.
    """
    chars = [secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUPS * CODE_GROUP_LEN)]
    groups = [
        ''.join(chars[i:i + CODE_GROUP_LEN])
        for i in range(0, len(chars), CODE_GROUP_LEN)
    ]
    return '-'.join(groups)


def canonical_code(code: str | None) -> str:
    """Strip the formatting people add back: spaces, dashes, wrong case.

    A code copied out of a password manager, retyped from paper, or pasted
    with a stray space should all still work — the entropy is in the letters,
    not the punctuation.
    """
    return ''.join(c for c in (code or '').upper() if c.isalnum())


def hash_recovery_code(code: str) -> str:
    """SHA-256 of the canonical form.

    Deliberately not a password KDF: this is a 98-bit random secret, not
    something a human chose, so there is no dictionary to slow an attacker
    down against and stretching would only cost the server time.
    """
    return hashlib.sha256(canonical_code(code).encode()).hexdigest()


def recovery_code_matches(code: str | None, stored_hash: str | None) -> bool:
    """Constant-time comparison of a supplied code against a stored hash."""
    if not code or not stored_hash:
        return False
    return hmac.compare_digest(hash_recovery_code(code), str(stored_hash).strip())
