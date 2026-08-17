import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from .config import get_settings

settings = get_settings()

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_token_payload",
    "decrypt_secret",
    "encrypt_secret",
    "new_token_id",
    "token_id_hash",
]


def encrypt_secret(value: str) -> str:
    """Fernet-encrypt an arbitrary secret string (e.g. a tool credential)."""
    return settings.get_fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Decrypt a value produced by :func:`encrypt_secret`.

    Raises ``cryptography.fernet.InvalidToken`` when the value is not valid
    ciphertext under the current key. Runtime plaintext fallback is not part of
    the current secret-storage contract.
    """
    return settings.get_fernet().decrypt(value.encode()).decode()


def _make_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(username: str, role: str = "user", token_version: int = 0) -> str:
    return _make_token(
        {"sub": username, "role": role, "type": "access", "ver": token_version},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def new_token_id() -> str:
    return secrets.token_urlsafe(32)


def token_id_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_refresh_token(
    username: str, token_version: int = 0, *, session_id: str, token_id: str
) -> str:
    return _make_token(
        {
            "sub": username,
            "type": "refresh",
            "ver": token_version,
            "sid": session_id,
            "jti": token_id,
        },
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token_payload(token: str, expected_type: str = "access") -> dict:
    """Validate a token and return its full payload (sub, ver, role, ...).

    Raises ``ValueError`` on invalid/expired/wrong-type tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp"]},
        )
        if payload.get("type") != expected_type:
            raise ValueError("Wrong token type")
        username: str = payload.get("sub")
        if not username:
            raise ValueError("Missing subject")
        return payload
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
