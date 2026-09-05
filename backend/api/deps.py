from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.rls_context import set_request_admin_context, set_request_tenant_context
from backend.core.security import decode_token_payload
from backend.models.user import User
from backend.repositories.permissions import get_user_page_permission, get_user_setting_permission, list_allowed_page_keys
from backend.repositories.users import get_user_by_username
from backend.schemas.tool_settings import ToolSettingsUpdate
from backend.services.tool_access_service import get_user_access_overrides
from backend.trading_agents.agents.tools.registry import registry

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

WEBSOCKET_APPLICATION_SUBPROTOCOL = "tradingagents.v1"
WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX = "tradingagents.jwt."


def get_websocket_application_subprotocol(offered_subprotocols: str | None) -> str | None:
    offered = {protocol.strip() for protocol in (offered_subprotocols or "").split(",")}
    if WEBSOCKET_APPLICATION_SUBPROTOCOL in offered:
        return WEBSOCKET_APPLICATION_SUBPROTOCOL
    return None


def get_websocket_access_token(offered_subprotocols: str | None) -> str | None:
    for protocol in (offered_subprotocols or "").split(","):
        protocol = protocol.strip()
        if protocol.startswith(WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX):
            token = protocol.removeprefix(WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX)
            if token:
                return token
    return None


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_user_from_access_token(token: str, db: AsyncSession) -> User:
    """Resolve an active user and establish request-local tenant DB context."""
    credentials_exc = _credentials_exception()
    try:
        payload = decode_token_payload(token, expected_type="access")
    except ValueError:
        raise credentials_exc from None
    username = payload.get("sub")
    if not username:
        raise credentials_exc
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_exc
    if payload.get("ver", 0) != getattr(user, "token_version", 0):
        raise credentials_exc

    if user.is_admin:
        await set_request_admin_context(db, user.id)
    else:
        await set_request_tenant_context(db, user.id)
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_from_access_token(token, db)
    from backend.core.log_handler import current_user_id

    current_user_id.set(user.id)
    # Authentication has fully materialized the User object and RLS context is
    # stored in AsyncSession.info. End the authentication transaction so a
    # handler whose first operation is network/LLM work does not inherit a
    # pinned DB connection. The RLS after_begin hook reapplies the same logical
    # context when the handler later opens its own transaction.
    await db.commit()
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def has_page_access(db: AsyncSession, user: User, page_key: str) -> bool:
    if user.is_admin or page_key == "settings":
        return True
    perm = await get_user_page_permission(db, user.id, page_key)
    return bool(perm and perm.allowed)


def require_page(page_key: str):
    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await has_page_access(db, current_user, page_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to page '{page_key}' is not permitted",
            )
        # Non-admin permission checks open a fresh transaction after auth.
        # Release it before entering the endpoint for the same connection-life
        # reason as get_current_user above.
        await db.commit()
        return current_user

    return _check


def require_any_page(*page_keys: str):
    if not page_keys:
        raise ValueError("require_any_page needs at least one page key")

    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_admin or "settings" in page_keys:
            return current_user

        allowed_pages = await list_allowed_page_keys(db, current_user.id)
        if allowed_pages.intersection(page_keys):
            await db.commit()
            return current_user

        joined = ", ".join(page_keys)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to one of these pages is required: {joined}",
        )

    return _check


async def enforce_setting_section_permission(db: AsyncSession, user: User, section: str) -> None:
    if user.is_admin:
        return
    permission = await get_user_setting_permission(db, user.id, section)
    if not permission or not permission.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to modify settings in section: {section}",
        )


async def enforce_tool_settings_permission(
    db: AsyncSession,
    user: User,
    body: ToolSettingsUpdate,
) -> dict[str, dict] | None:
    """Validate a tool mutation and return the access snapshot already loaded."""
    if user.is_admin:
        return None

    await enforce_setting_section_permission(db, user, "tools")
    access = await get_user_access_overrides(db, user.id)
    tool_access_map = access["tool_access"]
    field_access_map = access["field_access"]

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

            tool_field_access = field_access_map.get(tool_key, {})
            changed_fields = set(update.settings or {}) | set(update.reset_settings or [])
            for field_key in changed_fields:
                field_perms = tool_field_access.get(field_key, {})
                if not field_perms.get("can_view", True) or not field_perms.get("can_edit", True):
                    raise HTTPException(
                        status_code=403,
                        detail=f"You do not have permission to modify field '{field_key}' on tool '{tool_key}'.",
                    )

    return access