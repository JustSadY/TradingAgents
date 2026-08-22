"""Password hashing primitives.

Deliberately free of any ``backend.core.config`` import. Configuration
validation needs to recognise hash formats while ``Settings`` is still being
constructed, and ``core.security`` resolves settings at import time, so routing
that check through ``core.security`` would re-enter ``get_settings()``.
"""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

# Argon2 is the only supported password hash format. Keeping a single hashing
# backend removes the retired bcrypt verification/rehash compatibility path and
# avoids bcrypt's 72-byte password limit.
_password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_and_update_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """Verify *plain* and refresh an Argon2 hash when its parameters are stale."""
    try:
        return _password_hash.verify_and_update(plain, hashed)
    except (UnknownHashError, ValueError, TypeError):
        return False, None
