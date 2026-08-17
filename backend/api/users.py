from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db, require_admin, require_page
from backend.core.config import get_settings as _get_settings
from backend.models.user import User
from backend.repositories.permissions import list_allowed_page_keys, list_allowed_setting_sections
from backend.repositories.users import get_user_by_id
from backend.schemas.common import MessageResponse
from backend.schemas.user import (
    AgentAccessMap,
    AgentAccessUpdateResponse,
    ApiKeyProvidersResponse,
    ApiKeySet,
    PagePermissionsRead,
    PagePermissionsUpdate,
    ProfileUpdate,
    SettingPermissionsResponse,
    ToolAccessMap,
    ToolAccessPermsUpdate,
    ToolAccessUpdateResponse,
    ToolFieldAccessMap,
    ToolFieldAccessPermsUpdate,
    ToolFieldAccessUpdateResponse,
    UserAdminUpdate,
    UserCreate,
    UserPermissionsResponse,
    UserRead,
)
from backend.services.user_service import (
    CannotDeleteSelfError,
    EmailTakenError,
    UserNotFoundError,
    UserPolicyError,
    UsernameTakenError,
    create_managed_user,
    delete_managed_user,
    delete_user_api_key,
    list_user_api_key_providers,
    set_user_api_key,
    update_managed_user,
    update_profile,
)

router = APIRouter(prefix="/api/users", tags=["users"])

_USER_NOT_FOUND = "User not found"


@router.get("/me", response_model=UserRead)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.put("/me", response_model=UserRead, responses={400: {"description": "Email already in use"}})
async def update_me(
    body: ProfileUpdate,
    current_user: Annotated[User, Depends(require_page("profile"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await update_profile(
            db,
            current_user,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
        )
    except EmailTakenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/me/api-keys", response_model=ApiKeyProvidersResponse)
async def list_my_api_keys(current_user: Annotated[User, Depends(get_current_user)]):
    fernet = _get_settings().get_fernet()
    providers = list_user_api_key_providers(current_user, fernet)
    return {"providers": providers}


@router.put("/me/api-keys", response_model=MessageResponse)
async def set_my_api_key(
    body: ApiKeySet,
    current_user: Annotated[User, Depends(require_page("profile"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fernet = _get_settings().get_fernet()
    set_user_api_key(current_user, body.provider, body.api_key, fernet)
    await db.flush()
    return {"detail": f"API key for '{body.provider}' saved"}


@router.delete(
    "/me/api-keys/{provider}",
    response_model=MessageResponse,
    responses={404: {"description": "No key found for provider"}},
)
async def delete_my_api_key(
    provider: str,
    current_user: Annotated[User, Depends(require_page("profile"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fernet = _get_settings().get_fernet()
    deleted = delete_user_api_key(current_user, provider, fernet)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
    return {"detail": f"API key for '{provider}' deleted"}


@router.get("/me/permissions", response_model=PagePermissionsRead)
async def get_my_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from backend.core.constants import PAGE_KEYS

    if current_user.is_admin:
        return PagePermissionsRead(allowed_pages=PAGE_KEYS + ["admin"])
    allowed = sorted(await list_allowed_page_keys(db, current_user.id))
    if "settings" not in allowed:
        allowed.append("settings")
    return PagePermissionsRead(allowed_pages=allowed)


@router.get("/me/setting-permissions", response_model=SettingPermissionsResponse)
async def get_my_setting_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from backend.core.constants import SETTING_KEYS

    if current_user.is_admin:
        return {"allowed_settings": SETTING_KEYS}
    allowed = sorted(await list_allowed_setting_sections(db, current_user.id))
    return {"allowed_settings": allowed}


@router.get("", response_model=list[UserRead])
async def list_users_run(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from backend.repositories.users import list_users as _repo_list

    return await _repo_list(db)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "Username or email taken"}, 403: {"description": "Permission denied"}},
)
async def create_user(
    body: UserCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await create_managed_user(
            db,
            admin,
            username=body.username,
            password=body.password,
            email=body.email,
            display_name=body.display_name,
            role=body.role,
        )
    except (UsernameTakenError, EmailTakenError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except UserPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None


@router.put(
    "/{user_id}",
    response_model=UserRead,
    responses={403: {"description": "Permission denied"}, 404: {"description": _USER_NOT_FOUND}},
)
async def update_user(
    user_id: int,
    body: UserAdminUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await update_managed_user(
            db,
            admin,
            user_id,
            role=body.role,
            is_active=body.is_active,
            email=body.email,
            display_name=body.display_name,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except UserPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except EmailTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"description": "Cannot delete yourself"},
        403: {"description": "Permission denied"},
        404: {"description": _USER_NOT_FOUND},
    },
)
async def delete_user(
    user_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await delete_managed_user(db, admin, user_id)
    except CannotDeleteSelfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except UserPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None


@router.get("/{user_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.models.page_permission import ALL_PAGE_KEYS
    from backend.repositories.permissions import get_user_page_permissions_map

    perms = await get_user_page_permissions_map(db, user_id)
    full = {k: perms.get(k, False) for k in ALL_PAGE_KEYS}
    return {"user_id": user_id, "permissions": full}


@router.put("/{user_id}/permissions", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}})
async def set_user_permissions(
    user_id: int,
    body: PagePermissionsUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

    from backend.models.page_permission import ALL_PAGE_KEYS
    from backend.repositories.permissions import set_user_page_permission

    unknown = sorted(set(body.permissions) - set(ALL_PAGE_KEYS))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown page permission keys: {', '.join(unknown)}")
    for page_key, allowed in body.permissions.items():
        await set_user_page_permission(db, user_id, page_key, allowed)

    await db.flush()
    return {"detail": "Permissions updated"}


@router.get(
    "/{user_id}/api-keys", response_model=ApiKeyProvidersResponse, responses={404: {"description": _USER_NOT_FOUND}}
)
async def list_user_api_keys(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    fernet = _get_settings().get_fernet()
    providers = list_user_api_key_providers(user, fernet)
    return {"providers": providers}


@router.put("/{user_id}/api-keys", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}})
async def set_user_api_key_endpoint(
    user_id: int,
    body: ApiKeySet,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    fernet = _get_settings().get_fernet()
    set_user_api_key(user, body.provider, body.api_key, fernet)
    await db.flush()
    return {"detail": f"API key for '{body.provider}' saved for user {user.username}"}


@router.delete(
    "/{user_id}/api-keys/{provider}",
    response_model=MessageResponse,
    responses={404: {"description": "User or key not found"}},
)
async def delete_user_api_key_endpoint(
    user_id: int,
    provider: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    fernet = _get_settings().get_fernet()
    deleted = delete_user_api_key(user, provider, fernet)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
    await db.flush()
    return {"detail": f"API key for '{provider}' deleted for user {user.username}"}


@router.get(
    "/{user_id}/setting-permissions",
    response_model=UserPermissionsResponse,
    responses={404: {"description": _USER_NOT_FOUND}},
)
async def get_user_setting_permissions(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.core.constants import SETTING_KEYS
    from backend.repositories.permissions import get_user_setting_permissions_map

    perms = await get_user_setting_permissions_map(db, user_id)
    full = {k: perms.get(k, False) for k in SETTING_KEYS}
    return {"user_id": user_id, "permissions": full}


class SettingPermissionsUpdate(BaseModel):
    permissions: dict[str, bool]


@router.put(
    "/{user_id}/setting-permissions", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}}
)
async def set_user_setting_permissions(
    user_id: int,
    body: SettingPermissionsUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

    from backend.core.constants import SETTING_KEYS
    from backend.repositories.permissions import set_user_setting_permission

    unknown = sorted(set(body.permissions) - set(SETTING_KEYS))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown setting permission keys: {', '.join(unknown)}")
    for setting_key, allowed in body.permissions.items():
        await set_user_setting_permission(db, user_id, setting_key, allowed)

    await db.flush()
    return {"detail": "Setting permissions updated"}


@router.get("/{user_id}/agent-access", response_model=AgentAccessMap)
async def get_agent_access(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import get_user_agent_access

    return await get_user_agent_access(db, user_id)


class AgentAccessUpdate(BaseModel):
    agents: dict[str, bool]


@router.put("/{user_id}/agent-access", response_model=AgentAccessUpdateResponse)
async def set_agent_access(
    user_id: int,
    body: AgentAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import update_user_agent_access

    updated = await update_user_agent_access(db, user_id, body.agents)
    return {"detail": "Agent access updated", "agents": updated}


@router.get("/{user_id}/tool-access", response_model=ToolAccessMap)
async def get_tool_access(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import get_user_tool_access

    return await get_user_tool_access(db, user_id)


class ToolAccessUpdate(BaseModel):
    tools: dict[str, ToolAccessPermsUpdate]


@router.put("/{user_id}/tool-access", response_model=ToolAccessUpdateResponse)
async def set_tool_access(
    user_id: int,
    body: ToolAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import update_user_tool_access

    updated = await update_user_tool_access(
        db, user_id, {key: perms.model_dump(exclude_unset=True) for key, perms in body.tools.items()}
    )
    return {"detail": "Tool access updated", "tools": updated}


@router.get("/{user_id}/tool-field-access", response_model=ToolFieldAccessMap)
async def get_tool_field_access(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import get_user_tool_field_access

    return await get_user_tool_field_access(db, user_id)


class ToolFieldAccessUpdate(BaseModel):
    fields: dict[str, dict[str, ToolFieldAccessPermsUpdate]]


@router.put("/{user_id}/tool-field-access", response_model=ToolFieldAccessUpdateResponse)
async def set_tool_field_access(
    user_id: int,
    body: ToolFieldAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not await get_user_by_id(db, user_id):
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    from backend.services.tool_access_service import update_user_tool_field_access

    updated = await update_user_tool_field_access(
        db,
        user_id,
        {
            tool_key: {field_key: perms.model_dump(exclude_unset=True) for field_key, perms in fields.items()}
            for tool_key, fields in body.fields.items()
        },
    )
    return {"detail": "Tool field access updated", "fields": updated}
