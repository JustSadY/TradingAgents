from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
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

# Verified against when the username does not exist, so login latency does not
# reveal whether an account exists (timing-based user enumeration).
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, body.username)
    password_ok = verify_password(body.password, user.hashed_password if user else _DUMMY_PASSWORD_HASH)
    if not user or not password_ok or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    ver = getattr(user, "token_version", 0)
    return TokenResponse(
        access_token=create_access_token(user.username, role=user.role, token_version=ver),
        refresh_token=create_refresh_token(user.username, token_version=ver),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token_payload(body.refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None

    user = await get_user_by_username(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # A rotated/revoked refresh token (older version) can no longer be redeemed.
    ver = getattr(user, "token_version", 0)
    if payload.get("ver", 0) != ver:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    return TokenResponse(
        access_token=create_access_token(user.username, role=user.role, token_version=ver),
        refresh_token=create_refresh_token(user.username, token_version=ver),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke every token issued to the caller by bumping their token version."""
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    await db.commit()
