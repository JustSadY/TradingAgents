from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import decode_token
from backend.models.user import User
from backend.repositories.permissions import get_user_page_permission
from backend.repositories.users import get_user_by_username
from backend.schemas.tool_settings import ToolSettingsUpdate
from backend.services.tool_access_service import get_user_tool_access
from backend.trading_agents.agents.tools.registry import registry

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
        perm = await get_user_page_permission(db, current_user.id, page_key)
        if not perm or not perm.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to page '{page_key}' is not permitted",
            )
        return current_user

    return _check


async def enforce_tool_settings_permission(
    db: AsyncSession,
    user: User,
    body: ToolSettingsUpdate,
) -> None:
    """Raise 403/400 if *user* may not apply the tool changes in *body*.

    This must be called from inside the request handler, where the parsed body
    is available. It cannot be a FastAPI dependency: FastAPI does not inject a
    route's body model into a dependency parameter, so the previous
    dependency-based version received ``None`` and silently allowed everything.
    """
    if user.is_admin:
        return

    tool_access_map = await get_user_tool_access(db, user.id)

    for tool_key, update in body.tools.items():
        tool = registry.get(tool_key)
        if not tool:
            raise HTTPException(status_code=400, detail=f"Unknown tool key '{tool_key}'.")

        perms = tool_access_map.get(tool_key, {})
        if not perms.get("can_view", True):
            raise HTTPException(status_code=403, detail=f"You do not have permission to view tool '{tool_key}'.")

        if update.enabled is not None or update.reset_enabled:
            if not perms.get("can_enable", False):
                raise HTTPException(
                    status_code=403, detail=f"You do not have permission to enable/disable tool '{tool_key}'."
                )

        if update.settings is not None or update.reset_settings:
            if not perms.get("can_edit", False):
                raise HTTPException(
                    status_code=403, detail=f"You do not have permission to modify settings for tool '{tool_key}'."
                )
