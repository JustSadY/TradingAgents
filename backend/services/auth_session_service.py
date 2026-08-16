from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.rls_context import set_refresh_access_context
from backend.core.security import (
    create_refresh_token,
    decode_token_payload,
    new_token_id,
    token_id_hash,
)
from backend.models.user import User
from backend.repositories.refresh_sessions import (
    create_refresh_session,
    delete_refresh_sessions_for_user,
    get_refresh_session_for_update,
)
from backend.repositories.users import get_user_by_id

_REFRESH_GRACE_SECONDS = 15


class RefreshSessionError(ValueError):
    """Expected refresh-session rejection with a stable public detail string."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _decode_refresh(raw_token: str) -> tuple[dict[str, Any], str, str]:
    try:
        payload = decode_token_payload(raw_token, expected_type="refresh")
        session_id = str(payload["sid"])
        token_id = str(payload["jti"])
    except (ValueError, KeyError, TypeError):
        raise RefreshSessionError("Invalid refresh token") from None
    if not session_id or not token_id:
        raise RefreshSessionError("Invalid refresh token")
    return payload, session_id, token_id


async def issue_refresh_session(db: AsyncSession, user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    session_id, token_id = new_token_id(), new_token_id()
    await set_refresh_access_context(db, session_id=session_id, user_id=user.id)
    await create_refresh_session(
        db,
        session_id=session_id,
        user_id=user.id,
        current_jti_hash=token_id_hash(token_id),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return create_refresh_token(
        user.username,
        token_version=user.token_version,
        session_id=session_id,
        token_id=token_id,
    )


async def _persist_revocation(db: AsyncSession, session, now: datetime) -> None:
    if session.revoked_at is None:
        session.revoked_at = now
    # These rejections intentionally survive the HTTP 401. The request-scoped
    # get_db dependency rolls back on exceptions, so commit before raising.
    await db.flush()
    await db.commit()


async def rotate_refresh_session(db: AsyncSession, raw_token: str) -> tuple[User, str]:
    payload, session_id, token_id = _decode_refresh(raw_token)
    await set_refresh_access_context(db, session_id=session_id)
    session = await get_refresh_session_for_update(db, session_id)

    now = datetime.now(UTC)
    presented_hash = token_id_hash(token_id)
    valid_current = bool(session and presented_hash == session.current_jti_hash)
    valid_grace = bool(
        session
        and session.previous_jti_hash == presented_hash
        and _aware(session.previous_valid_until)
        and _aware(session.previous_valid_until) >= now
    )

    if (
        not session
        or session.revoked_at
        or _aware(session.expires_at) <= now
        or not (valid_current or valid_grace)
    ):
        if session and session.revoked_at is None:
            await _persist_revocation(db, session, now)
        raise RefreshSessionError("Refresh session expired or reused")

    user = await get_user_by_id(db, session.user_id)
    if not user or not user.is_active or payload.get("ver", 0) != user.token_version:
        await _persist_revocation(db, session, now)
        raise RefreshSessionError("Refresh token has been revoked")

    rotated_token_id = new_token_id()
    session.previous_jti_hash = session.current_jti_hash
    session.previous_valid_until = now + timedelta(seconds=_REFRESH_GRACE_SECONDS)
    session.current_jti_hash = token_id_hash(rotated_token_id)
    session.updated_at = now
    await db.flush()

    refresh_token = create_refresh_token(
        user.username,
        token_version=user.token_version,
        session_id=session_id,
        token_id=rotated_token_id,
    )
    return user, refresh_token


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> bool:
    try:
        _, session_id, _ = _decode_refresh(raw_token)
    except RefreshSessionError:
        return False

    await set_refresh_access_context(db, session_id=session_id)
    session = await get_refresh_session_for_update(db, session_id)
    if session is None:
        return False
    session.revoked_at = datetime.now(UTC)
    await db.flush()
    return True


async def revoke_user_refresh_sessions(db: AsyncSession, user: User) -> None:
    await delete_refresh_sessions_for_user(db, user.id)
    await db.flush()
