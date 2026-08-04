from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_user_from_access_token
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token_payload,
    hash_password,
    new_token_id,
    token_id_hash,
    verify_password,
)
from backend.models.refresh_session import RefreshSession
from backend.models.user import User
from backend.repositories.users import get_user_by_username
from backend.schemas.auth import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")
_REFRESH_COOKIE_NAME = "ta_refresh"
_REFRESH_COOKIE_PATH = "/auth"
_REFRESH_GRACE_SECONDS = 15


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME, value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=settings.ENVIRONMENT.strip().lower() == "production",
        samesite="lax", path=_REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME, httponly=True,
        secure=settings.ENVIRONMENT.strip().lower() == "production",
        samesite="lax", path=_REFRESH_COOKIE_PATH,
    )


async def _issue_session(db: AsyncSession, user: User) -> str:
    now = datetime.now(UTC)
    sid, jti = new_token_id(), new_token_id()
    db.add(RefreshSession(
        id=sid, user_id=user.id, current_jti_hash=token_id_hash(jti),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.flush()
    return create_refresh_token(user.username, token_version=user.token_version, session_id=sid, token_id=jti)


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await get_user_by_username(db, body.username)
    password_ok = verify_password(body.password, user.hashed_password if user else _DUMMY_PASSWORD_HASH)
    if not user or not password_ok or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = await _issue_session(db, user)
    _set_refresh_cookie(response, token)
    return TokenResponse(access_token=create_access_token(user.username, role=user.role, token_version=user.token_version))


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("30/minute")
async def refresh(request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)], body: RefreshRequest | None = None):
    raw = request.cookies.get(_REFRESH_COOKIE_NAME) or (body.refresh_token if body else None)
    if not raw:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token required")
    try:
        payload = decode_token_payload(raw, expected_type="refresh")
        sid, jti = str(payload["sid"]), str(payload["jti"])
    except (ValueError, KeyError, TypeError):
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())
    session = row.scalar_one_or_none()
    now = datetime.now(UTC)
    presented = token_id_hash(jti)
    valid_current = bool(session and presented == session.current_jti_hash)
    valid_grace = bool(
        session and session.previous_jti_hash == presented
        and _aware(session.previous_valid_until) and _aware(session.previous_valid_until) >= now
    )
    if not session or session.revoked_at or _aware(session.expires_at) <= now or not (valid_current or valid_grace):
        if session and not session.revoked_at:
            session.revoked_at = now  # replay outside the short multi-tab grace window
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh session expired or reused")

    user_row = await db.execute(select(User).where(User.id == session.user_id))
    user = user_row.scalar_one_or_none()
    if not user or not user.is_active or payload.get("ver", 0) != user.token_version:
        session.revoked_at = now
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    new_jti = new_token_id()
    session.previous_jti_hash = session.current_jti_hash
    session.previous_valid_until = now + timedelta(seconds=_REFRESH_GRACE_SECONDS)
    session.current_jti_hash = token_id_hash(new_jti)
    session.updated_at = now
    await db.flush()
    token = create_refresh_token(user.username, token_version=user.token_version, session_id=sid, token_id=new_jti)
    _set_refresh_cookie(response, token)
    return TokenResponse(access_token=create_access_token(user.username, role=user.role, token_version=user.token_version))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    raw = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw:
        try:
            payload = decode_token_payload(raw, expected_type="refresh")
            sid = str(payload.get("sid", ""))
            if sid:
                row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())
                session = row.scalar_one_or_none()
                if session:
                    session.revoked_at = datetime.now(UTC)
        except ValueError:
            pass
    else:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user = await get_user_from_access_token(token, db)
                await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
            except HTTPException:
                pass
    _clear_refresh_cookie(response)
