"""Password hashing primitives.

Deliberately free of any ``backend.core.config`` import. Configuration
validation needs to recognise hash formats while ``Settings`` is still being
constructed, and ``core.security`` resolves settings at import time, so routing
that check through ``core.security`` would re-enter ``get_settings()``.
"""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

# Argon2 hashes every new password. bcrypt stays registered so hashes written
# before this migration keep verifying — both the ``users.hashed_password``
# column and operator-supplied ``ADMIN_PASSWORD_HASH`` values in .env.
# ``verify_and_update_password`` upgrades them to Argon2 on next login.
#
# Argon2 also removes bcrypt's 72-*byte* input limit, which a password of ~37
# Turkish characters already exceeds even though it is well inside the 128
# *character* bound the API schemas allow.
_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def is_supported_password_hash(value: str) -> bool:
    """True when *value* is in a hash format this application can verify.

    Used to validate operator-supplied ``ADMIN_PASSWORD_HASH`` values, which may
    legitimately be either bcrypt (written before this migration) or Argon2.
    """
    return any(hasher.identify(value) for hasher in _password_hash.hashers)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(plain, hashed)
    except (UnknownHashError, ValueError, TypeError):
        # Unrecognised hash format, or an over-long input measured against a
        # legacy bcrypt hash. Neither can be a successful login.
        return False


def verify_and_update_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """Verify *plain*, returning ``(ok, upgraded_hash)``.

    ``upgraded_hash`` is non-None when the stored hash used a superseded scheme
    or outdated parameters, and the caller should persist it.
    """
    try:
        return _password_hash.verify_and_update(plain, hashed)
    except (UnknownHashError, ValueError, TypeError):
        return False, None
