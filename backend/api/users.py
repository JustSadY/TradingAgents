from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db, require_admin, require_page
from backend.models.user import User
from backend.schemas.common import MessageResponse
from backend.schemas.user import (
    AgentAccessMap,
    AgentAccessUpdate,
    AgentAccessUpdateResponse,
    ApiKeyProvidersResponse,
    ApiKeySet,
    PagePermissionsRead,
    PagePermissionsUpdate,
    ProfileUpdate,
    SettingPermissionsResponse,
    SettingPermissionsUpdate,
    ToolAccessMap,
    ToolAccessUpdate,
    ToolAccessUpdateResponse,
    ToolFieldAccessMap,
    ToolFieldAccessUpdate,
    ToolFieldAccessUpdateResponse,
    UserAdminUpdate,
    UserCreate,
    UserPermissionsResponse,
    UserRead,
)
from backend.services.user_service import (
    CannotDeleteSelfError,
    EmailTakenError,
    UnknownPermissionKeysError,
    UsernameTakenError,
    UserNotFoundError,
    UserPolicyError,
    create_managed_user,
    delete_managed_user,
    get_effective_page_permissions,
    get_effective_setting_permissions,
    get_managed_page_permissions,
    get_managed_setting_permissions,
    get_user_or_raise,
    list_managed_users,
    list_stored_api_key_providers,
    remove_stored_api_key,
    save_stored_api_key,
    set_managed_page_permissions,
    set_managed_setting_permissions,
    update_managed_user,
    update_profile,
)

router = APIRouter(prefix="/api/users", tags=["users"])

_USER_NOT_FOUND = "User not found"


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    try:
        return await get_user_or_raise(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


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
    return {"providers": list_stored_api_key_providers(current_user)}


@router.put("/me/api-keys", response_model=MessageResponse)
async def set_my_api_key(
    body: ApiKeySet,
    current_user: Annotated[User, Depends(require_page("profile"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await save_stored_api_key(db, current_user, body.provider, body.api_key)
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
    deleted = await remove_stored_api_key(db, current_user, provider)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
    return {"detail": f"API key for '{provider}' deleted"}


@router.get("/me/permissions", response_model=PagePermissionsRead)
async def get_my_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return PagePermissionsRead(allowed_pages=await get_effective_page_permissions(db, current_user))


@router.get("/me/setting-permissions", response_model=SettingPermissionsResponse)
async def get_my_setting_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return {"allowed_settings": await get_effective_setting_permissions(db, current_user)}


@router.get("", response_model=list[UserRead])
async def list_users_run(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await list_managed_users(db)


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
    try:
        permissions = await get_managed_page_permissions(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"user_id": user_id, "permissions": permissions}


@router.put("/{user_id}/permissions", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}})
async def set_user_permissions(
    user_id: int,
    body: PagePermissionsUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await set_managed_page_permissions(db, user_id, body.permissions)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except UnknownPermissionKeysError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"detail": "Permissions updated"}


@router.get(
    "/{user_id}/api-keys", response_model=ApiKeyProvidersResponse, responses={404: {"description": _USER_NOT_FOUND}}
)
async def list_user_api_keys(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _get_user_or_404(db, user_id)
    return {"providers": list_stored_api_key_providers(user)}


@router.put("/{user_id}/api-keys", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}})
async def set_user_api_key_endpoint(
    user_id: int,
    body: ApiKeySet,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await _get_user_or_404(db, user_id)
    await save_stored_api_key(db, user, body.provider, body.api_key)
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
    user = await _get_user_or_404(db, user_id)
    deleted = await remove_stored_api_key(db, user, provider)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
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
    try:
        permissions = await get_managed_setting_permissions(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"user_id": user_id, "permissions": permissions}


@router.put(
    "/{user_id}/setting-permissions", response_model=MessageResponse, responses={404: {"description": _USER_NOT_FOUND}}
)
async def set_user_setting_permissions(
    user_id: int,
    body: SettingPermissionsUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await set_managed_setting_permissions(db, user_id, body.permissions)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except UnknownPermissionKeysError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"detail": "Setting permissions updated"}


@router.get("/{user_id}/agent-access", response_model=AgentAccessMap)
async def get_agent_access(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_user_or_404(db, user_id)
    from backend.services.tool_access_service import get_user_agent_access

    return await get_user_agent_access(db, user_id)


@router.put("/{user_id}/agent-access", response_model=AgentAccessUpdateResponse)
async def set_agent_access(
    user_id: int,
    body: AgentAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_user_or_404(db, user_id)
    from backend.services.tool_access_service import update_user_agent_access

    updated = await update_user_agent_access(db, user_id, body.agents)
    return {"detail": "Agent access updated", "agents": updated}


@router.get("/{user_id}/tool-access", response_model=ToolAccessMap)
async def get_tool_access(
    user_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_user_or_404(db, user_id)
    from backend.services.tool_access_service import get_user_tool_access

    return await get_user_tool_access(db, user_id)


@router.put("/{user_id}/tool-access", response_model=ToolAccessUpdateResponse)
async def set_tool_access(
    user_id: int,
    body: ToolAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_user_or_404(db, user_id)
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
    await _get_user_or_404(db, user_id)
    from backend.services.tool_access_service import get_user_tool_field_access

    return await get_user_tool_field_access(db, user_id)


@router.put("/{user_id}/tool-field-access", response_model=ToolFieldAccessUpdateResponse)
async def set_tool_field_access(
    user_id: int,
    body: ToolFieldAccessUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_user_or_404(db, user_id)
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
