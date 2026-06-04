from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.core.security import decode_token
from backend.models.user import User
from backend.repositories.users import get_user_by_username
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        username = decode_token(token, expected_type="access")
    except ValueError:
        raise credentials_exc
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_exc
    return user
async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
def require_page(page_key: str):
    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_admin:
            return current_user
        if page_key == "settings":
            return current_user
        from backend.models.page_permission import UserPagePermission
        result = await db.execute(
            select(UserPagePermission)
            .where(UserPagePermission.user_id == current_user.id)
            .where(UserPagePermission.page_key == page_key)
        )
        perm = result.scalar_one_or_none()
        if not perm or not perm.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to page '{page_key}' is not permitted",
            )
        return current_user
    return _check
