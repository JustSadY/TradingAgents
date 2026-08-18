from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_user_from_access_token
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.core.password_hashing import hash_password, verify_and_update_password
from backend.core.security import create_access_token
from backend.repositories.users import get_user_by_username
from backend.schemas.auth import LoginRequest, SetupRequest, SetupStatusResponse, TokenResponse
from backend.services.auth_session_service import (
    AuthSessionError,
    issue_refresh_session,
    revoke_refresh_token,
    revoke_user_refresh_sessions,
    rotate_refresh_session,
)
from backend.services.first_run_service import (
    SetupAlreadyCompletedError,
    create_first_owner,
    owner_setup_required,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")
_REFRESH_COOKIE_NAME = "ta_refresh"
_REFRESH_COOKIE_PATH = "/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
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


@router.get("/setup-status", response_model=SetupStatusResponse)
async def setup_status(db: Annotated[AsyncSession, Depends(get_db)]):
    """Whether the login screen should offer first-run owner registration."""
    return SetupStatusResponse(setup_required=await owner_setup_required(db))


@router.post("/setup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def setup(
    request: Request,
    response: Response,
    body: SetupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Register the Server Owner on an empty installation and sign it in.

    Closed for good once any account exists — it is a bootstrap route, not a
    public sign-up.
    """
    try:
        user = await create_first_owner(
            username=body.username,
            password=body.password,
            email=body.email,
            display_name=body.display_name,
        )
    except SetupAlreadyCompletedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    refresh_token = await issue_refresh_session(db, user)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            user.username,
            role=user.role,
            token_version=user.token_version,
        )
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_username(db, body.username)
    password_ok, upgraded_hash = verify_and_update_password(
        body.password,
        user.hashed_password if user else _DUMMY_PASSWORD_HASH,
    )
    if not user or not password_ok or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if upgraded_hash:
        user.hashed_password = upgraded_hash

    refresh_token = await issue_refresh_session(db, user)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            user.username,
            role=user.role,
            token_version=user.token_version,
        )
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not raw_token:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token required")

    try:
        user, rotated_refresh_token = await rotate_refresh_session(db, raw_token)
    except AuthSessionError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail=exc.detail) from None

    _set_refresh_cookie(response, rotated_refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            user.username,
            role=user.role,
            token_version=user.token_version,
        )
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw_refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        await revoke_refresh_token(db, raw_refresh_token)
    else:
        authorization = request.headers.get("authorization", "")
        scheme, _, access_token = authorization.partition(" ")
        if scheme.lower() == "bearer" and access_token:
            try:
                user = await get_user_from_access_token(access_token, db)
                await revoke_user_refresh_sessions(db, user)
            except HTTPException:
                pass

    _clear_refresh_cookie(response)
