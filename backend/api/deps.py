from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import decode_token_payload
from backend.models.user import User
from backend.repositories.permissions import get_user_page_permission, get_user_setting_permission
from backend.repositories.users import get_user_by_username
from backend.schemas.tool_settings import ToolSettingsUpdate
from backend.services.tool_access_service import get_user_tool_access, get_user_tool_field_access
from backend.trading_agents.agents.tools.registry import registry

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

WEBSOCKET_APPLICATION_SUBPROTOCOL = "tradingagents.v1"
WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX = "tradingagents.jwt."

def get_websocket_application_subprotocol(offered_subprotocols: str | None) -> str | None:
    """Return the fixed response protocol when the client offered it.

    Analysis streams require this protocol in addition to the private JWT
    protocol.  The JWT-bearing offer is deliberately never returned here:
    selecting it would expose credentials in the 101 response headers.
    """
    offered = {protocol.strip() for protocol in (offered_subprotocols or "").split(",")}
    if WEBSOCKET_APPLICATION_SUBPROTOCOL in offered:
        return WEBSOCKET_APPLICATION_SUBPROTOCOL
    return None

def get_websocket_access_token(
    offered_subprotocols: str | None,
) -> str | None:
    """Return a JWT supplied through the WebSocket handshake.

    Tokens are accepted only from the private ``Sec-WebSocket-Protocol``
    offer.  Query-string credentials are intentionally unsupported because
    normal proxy and access logs retain URLs.  The returned token still passes
    the normal JWT validation in :func:`get_user_from_access_token`.
    """
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
    """Resolve an active user from an access token, including revocation.

    HTTP dependencies and WebSocket handshakes use this exact check so a
    token-version bump (logout/password reset) invalidates both channels at
    once rather than leaving a live WebSocket usable until expiry.
    """
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
    return user

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_from_access_token(token, db)
    from backend.core.log_handler import current_user_id

    current_user_id.set(user.id)
    return user

def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

async def has_page_access(db: AsyncSession, user: User, page_key: str) -> bool:
    """Return whether ``user`` may use a page-backed capability.

    Page permissions are an API authorization boundary, not only a React
    navigation hint.  Keep the check reusable for WebSockets, which cannot
    use regular FastAPI HTTP dependencies.
    """
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
        return current_user

    return _check

def require_any_page(*page_keys: str):
    """Require at least one page entitlement for shared read endpoints."""
    if not page_keys:
        raise ValueError("require_any_page needs at least one page key")

    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        for page_key in page_keys:
            if await has_page_access(db, current_user, page_key):
                return current_user
        joined = ", ".join(page_keys)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to one of these pages is required: {joined}",
        )

    return _check

async def enforce_setting_section_permission(db: AsyncSession, user: User, section: str) -> None:
    """Require a non-admin to hold the named settings-section entitlement.

    Settings pages are deliberately always navigable so users can inspect
    their profile/configuration, but mutation endpoints must not let a hidden
    section be modified through a direct HTTP call.
    """
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
) -> None:
    """Raise 403/400 if *user* may not apply the tool changes in *body*.

    This must be called from inside the request handler, where the parsed body
    is available. It cannot be a FastAPI dependency: FastAPI does not inject a
    route's body model into a dependency parameter, so the previous
    dependency-based version received ``None`` and silently allowed everything.
    """
    if user.is_admin:
        return

    await enforce_setting_section_permission(db, user, "tools")

    tool_access_map = await get_user_tool_access(db, user.id)
    field_access_map = await get_user_tool_field_access(db, user.id)

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
