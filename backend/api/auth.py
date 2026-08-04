from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
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
    verify_password,
)
from backend.models.user import User
from backend.repositories.users import get_user_by_username
from backend.schemas.auth import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")
_REFRESH_COOKIE_NAME = "ta_refresh"
_REFRESH_COOKIE_PATH = "/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Store the rotating refresh credential outside JavaScript reach."""
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.ENVIRONMENT.strip().lower() == "production",
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.ENVIRONMENT.strip().lower() == "production",
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
    )


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_username(db, body.username)
    password_ok = verify_password(body.password, user.hashed_password if user else _DUMMY_PASSWORD_HASH)
    if not user or not password_ok or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    ver = getattr(user, "token_version", 0)
    _set_refresh_cookie(response, create_refresh_token(user.username, token_version=ver))
    return TokenResponse(access_token=create_access_token(user.username, role=user.role, token_version=ver))


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: RefreshRequest | None = None,
):
    # Cookie is authoritative. The optional body token keeps non-browser/API
    # clients compatible while the web UI migrates to HttpOnly cookies.
    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME) or (body.refresh_token if body else None)
    if not refresh_token:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")

    try:
        payload = decode_token_payload(refresh_token, expected_type="refresh")
    except ValueError:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None

    # Validate against the account-wide revocation generation.  Do not advance
    # that generation on a normal refresh: doing so makes two browser tabs
    # continuously invalidate each other's access tokens.  Logout/password
    # reset still increments token_version and revokes every outstanding token.
    row = await db.execute(select(User).where(User.username == payload["sub"]))
    user = row.scalar_one_or_none()
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    ver = getattr(user, "token_version", 0)
    if payload.get("ver", 0) != ver:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    _set_refresh_cookie(response, create_refresh_token(user.username, token_version=ver))
    return TokenResponse(access_token=create_access_token(user.username, role=user.role, token_version=ver))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Revoke the active session when resolvable and always clear its cookie.

    Logout must still work after the short-lived access token expires; otherwise
    a failed 401 leaves the valid HttpOnly refresh cookie in the browser and a
    reload silently signs the user back in.
    """
    user = None
    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if refresh_token:
        try:
            payload = decode_token_payload(refresh_token, expected_type="refresh")
            candidate = await get_user_by_username(db, payload.get("sub", ""))
            if candidate and candidate.is_active and payload.get("ver", 0) == getattr(candidate, "token_version", 0):
                user = candidate
        except ValueError:
            pass

    if user is None:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user = await get_user_from_access_token(token, db)
            except HTTPException:
                pass

    if user is not None:
        user.token_version = (getattr(user, "token_version", 0) or 0) + 1
    _clear_refresh_cookie(response)
