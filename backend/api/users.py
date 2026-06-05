import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.api.deps import get_current_user, require_admin, get_db
from backend.core.config import get_settings as _get_settings
from backend.core.security import hash_password
from backend.models.user import User
from backend.models.page_permission import UserPagePermission, UserSettingPermission, ALL_PAGE_KEYS
from backend.schemas.user import (
    UserCreate, UserRead, ProfileUpdate, UserAdminUpdate,
    ApiKeySet, PagePermissionsUpdate, PagePermissionsRead,
)
from backend.services.user_service import (
    set_user_api_key, delete_user_api_key, list_user_api_key_providers,
)
router = APIRouter(prefix="/api/users", tags=["users"])
_logger = logging.getLogger(__name__)
@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
@router.put("/me", response_model=UserRead)
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.email is not None:
        result = await db.execute(
            select(User).where(User.email == body.email).where(User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = body.email
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.password:
        current_user.hashed_password = hash_password(body.password)
    return current_user
@router.get("/me/api-keys")
async def list_my_api_keys(current_user: User = Depends(get_current_user)):
    fernet = _get_settings().get_fernet()
    providers = list_user_api_key_providers(current_user, fernet)
    return {"providers": providers}
@router.put("/me/api-keys")
async def set_my_api_key(
    body: ApiKeySet,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fernet = _get_settings().get_fernet()
    set_user_api_key(current_user, body.provider, body.api_key, fernet)
    return {"detail": f"API key for '{body.provider}' saved"}
@router.delete("/me/api-keys/{provider}")
async def delete_my_api_key(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fernet = _get_settings().get_fernet()
    deleted = delete_user_api_key(current_user, provider, fernet)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
    return {"detail": f"API key for '{provider}' deleted"}
@router.get("/me/permissions", response_model=PagePermissionsRead)
async def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.is_admin:
        return PagePermissionsRead(allowed_pages=ALL_PAGE_KEYS + ["admin", "settings"])
    result = await db.execute(
        select(UserPagePermission)
        .where(UserPagePermission.user_id == current_user.id)
        .where(UserPagePermission.allowed == True)
    )
    perms = result.scalars().all()
    allowed = [p.page_key for p in perms] + ["settings"]
    return PagePermissionsRead(allowed_pages=allowed)
@router.get("", response_model=list[UserRead])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()
@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")
    if body.email:
        result = await db.execute(select(User).where(User.email == body.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
    if body.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assigning the Server Owner role is prohibited."
        )
    if body.role != "user" and _.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Server Owner can create administrator accounts."
        )
    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        email=body.email,
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    db.add(UserPagePermission(user_id=user.id, page_key="dashboard", allowed=True))
    db.add(UserPagePermission(user_id=user.id, page_key="portfolio", allowed=True))
    for s_key in ["general", "llm", "risk", "webhooks", "cron", "presets"]:
        db.add(UserSettingPermission(user_id=user.id, setting_key=s_key, allowed=True))
    await db.flush()
    return user
@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    body: UserAdminUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "owner":
        if body.role is not None and body.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The Server Owner role is immutable and cannot be demoted."
            )
        if body.is_active is not None and body.is_active != user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The Server Owner account cannot be deactivated."
            )
    if body.role is not None:
        if body.role == "owner" and user.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Assigning the Server Owner role is prohibited."
            )
        if admin.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Server Owner can modify user roles or promote/demote administrators."
            )
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.email is not None:
        user.email = body.email
    if body.display_name is not None:
        user.display_name = body.display_name
    return user
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The Server Owner account cannot be deleted."
        )
    # Remove user watchlist cron job if exists
    try:
        from backend.services.cron_service import get_cron_service
        cron = get_cron_service()
        if cron:
            job_id = f"watchlist_scan_user_{user_id}"
            if cron.scheduler.get_job(job_id):
                cron.scheduler.remove_job(job_id)
                _logger.info("Successfully removed watchlist scan cron job for deleted user %d", user_id)
    except Exception as e:
        _logger.error("Failed to remove cron job for user %d on deletion: %s", user_id, e)

    await db.delete(user)
@router.get("/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPagePermission).where(UserPagePermission.user_id == user_id)
    )
    perms = {p.page_key: p.allowed for p in result.scalars().all()}
    full = {k: perms.get(k, False) for k in ALL_PAGE_KEYS}
    return {"user_id": user_id, "permissions": full}
@router.put("/{user_id}/permissions")
async def set_user_permissions(
    user_id: int,
    body: PagePermissionsUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    for page_key, allowed in body.permissions.items():
        if page_key not in ALL_PAGE_KEYS:
            continue
        result = await db.execute(
            select(UserPagePermission)
            .where(UserPagePermission.user_id == user_id)
            .where(UserPagePermission.page_key == page_key)
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = UserPagePermission(user_id=user_id, page_key=page_key, allowed=allowed)
            db.add(perm)
        else:
            perm.allowed = allowed
    await db.flush()
    return {"detail": "Permissions updated"}
@router.get("/{user_id}/api-keys")
async def list_user_api_keys(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    fernet = _get_settings().get_fernet()
    providers = list_user_api_key_providers(user, fernet)
    return {"providers": providers}
@router.put("/{user_id}/api-keys")
async def set_user_api_key_endpoint(
    user_id: int,
    body: ApiKeySet,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    fernet = _get_settings().get_fernet()
    set_user_api_key(user, body.provider, body.api_key, fernet)
    await db.flush()
    return {"detail": f"API key for '{body.provider}' saved for user {user.username}"}
@router.delete("/{user_id}/api-keys/{provider}")
async def delete_user_api_key_endpoint(
    user_id: int,
    provider: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    fernet = _get_settings().get_fernet()
    deleted = delete_user_api_key(user, provider, fernet)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for provider '{provider}'")
    await db.flush()
    return {"detail": f"API key for '{provider}' deleted for user {user.username}"}
@router.get("/me/setting-permissions")
async def get_my_setting_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.is_admin:
        return {"allowed_settings": ["general", "llm", "risk", "webhooks", "cron", "presets"]}
    result = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == current_user.id)
        .where(UserSettingPermission.allowed == True)
    )
    perms = result.scalars().all()
    allowed = [p.setting_key for p in perms]
    return {"allowed_settings": allowed}
@router.get("/{user_id}/setting-permissions")
async def get_user_setting_permissions(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(
        select(UserSettingPermission).where(UserSettingPermission.user_id == user_id)
    )
    perms = {p.setting_key: p.allowed for p in result.scalars().all()}
    full = {k: perms.get(k, False) for k in ["general", "llm", "risk", "webhooks", "cron", "presets"]}
    return {"user_id": user_id, "permissions": full}
from pydantic import BaseModel
class SettingPermissionsUpdate(BaseModel):
    permissions: dict[str, bool]
@router.put("/{user_id}/setting-permissions")
async def set_user_setting_permissions(
    user_id: int,
    body: SettingPermissionsUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    for setting_key, allowed in body.permissions.items():
        if setting_key not in ["general", "llm", "risk", "webhooks", "cron", "presets"]:
            continue
        result = await db.execute(
            select(UserSettingPermission)
            .where(UserSettingPermission.user_id == user_id)
            .where(UserSettingPermission.setting_key == setting_key)
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = UserSettingPermission(user_id=user_id, setting_key=setting_key, allowed=allowed)
            db.add(perm)
        else:
            perm.allowed = allowed
    await db.flush()
    return {"detail": "Setting permissions updated"}


@router.get("/{user_id}/agent-access")
async def get_agent_access(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import get_user_agent_access
    return await get_user_agent_access(db, user_id)


class AgentAccessUpdate(BaseModel):
    agents: dict[str, bool]


@router.put("/{user_id}/agent-access")
async def set_agent_access(
    user_id: int,
    body: AgentAccessUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import update_user_agent_access
    updated = await update_user_agent_access(db, user_id, body.agents)
    return {"detail": "Agent access updated", "agents": updated}


@router.get("/{user_id}/tool-access")
async def get_tool_access(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import get_user_tool_access
    return await get_user_tool_access(db, user_id)


class ToolAccessUpdate(BaseModel):
    tools: dict[str, dict]


@router.put("/{user_id}/tool-access")
async def set_tool_access(
    user_id: int,
    body: ToolAccessUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import update_user_tool_access
    updated = await update_user_tool_access(db, user_id, body.tools)
    return {"detail": "Tool access updated", "tools": updated}


@router.get("/{user_id}/tool-field-access")
async def get_tool_field_access(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import get_user_tool_field_access
    return await get_user_tool_field_access(db, user_id)


class ToolFieldAccessUpdate(BaseModel):
    fields: dict[str, dict[str, dict]]


@router.put("/{user_id}/tool-field-access")
async def set_tool_field_access(
    user_id: int,
    body: ToolFieldAccessUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_access_service import update_user_tool_field_access
    updated = await update_user_tool_field_access(db, user_id, body.fields)
    return {"detail": "Tool field access updated", "fields": updated}
