from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
from jose import JWTError, jwt

from .config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _make_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(username: str, role: str = "user", token_version: int = 0) -> str:
    return _make_token(
        {"sub": username, "role": role, "type": "access", "ver": token_version},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(username: str, token_version: int = 0) -> str:
    return _make_token(
        {"sub": username, "type": "refresh", "ver": token_version},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str = "access") -> str | None:
    """Validate a token and return its subject (username).

    Kept for callers that only need the username; use ``decode_token_payload``
    when the token version must also be checked.
    """
    return decode_token_payload(token, expected_type)["sub"]


def decode_token_payload(token: str, expected_type: str = "access") -> dict:
    """Validate a token and return its full payload (sub, ver, role, ...)."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != expected_type:
            raise ValueError("Wrong token type")
        username: str = payload.get("sub")
        if not username:
            raise ValueError("Missing subject")
        return payload
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


