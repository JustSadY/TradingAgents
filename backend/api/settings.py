import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.settings import SettingsRead, SettingsUpdate
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate
from backend.schemas.agent_settings import AgentSettingsRead, AgentSettingsUpdate
from backend.api.deps import get_current_user, require_admin, check_tool_settings_permission
from backend.repositories.permissions import list_allowed_setting_sections
from backend.repositories.users import get_user_by_id
from backend.services.settings_service import (
    get_or_create_settings,
    settings_to_read,
    apply_settings_update,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm-catalog")
async def get_llm_catalog(_: User = Depends(get_current_user)):
    from backend.trading_agents.llm_clients.model_catalog import MODEL_OPTIONS
    return {
        provider: [{"label": label, "value": value} for label, value in opts]
        for provider, opts in MODEL_OPTIONS.items()
    }


@router.get("", response_model=SettingsRead)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = await get_or_create_settings(db, current_user)
    return settings_to_read(settings)


async def _check_section_permissions(db: AsyncSession, user: User, body: SettingsUpdate) -> None:
    """Non-admins may only edit settings sections explicitly granted to them, and
    never advanced engine settings."""
    from backend.models.page_permission import SECTION_FIELDS
    allowed_sections = await list_allowed_setting_sections(db, user.id)
    attempted = body.model_dump(exclude_unset=True)
    for section, fields in SECTION_FIELDS.items():
        if any(f in attempted for f in fields) and section not in allowed_sections:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to modify settings in section: {section}",
            )
    advanced_fields = [
        "max_recur_limit",
    ]
    if any(f in attempted for f in advanced_fields):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Advanced engine settings can only be modified by administrators.",
        )


@router.put("", response_model=SettingsRead)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = await get_or_create_settings(db, current_user)
    if not current_user.is_admin:
        await _check_section_permissions(db, current_user, body)
    settings = await apply_settings_update(db, settings, body)
    return settings_to_read(settings)


class WebhookTestRequest(BaseModel):
    url: str


@router.post("/test-webhook")
async def test_webhook(body: WebhookTestRequest, _: User = Depends(get_current_user)):
    payload = {
        "text": "TradingAgents webhook testi başarılı! ✓",
        "content": "TradingAgents webhook testi başarılı! ✓",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(body.url, json=payload)
            if r.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"Webhook yanıtı: {r.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


async def _require_target_user(db: AsyncSession, user_id: int) -> User:
    target_user = await get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    return target_user


@router.get("/users/{user_id}", response_model=SettingsRead)
async def get_user_settings_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    settings = await get_or_create_settings(db, target_user)
    return settings_to_read(settings)


@router.put("/users/{user_id}", response_model=SettingsRead)
async def update_user_settings_by_id(
    user_id: int,
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    settings = await get_or_create_settings(db, target_user)
    settings = await apply_settings_update(db, settings, body)
    return settings_to_read(settings)


@router.get("/users/{user_id}/tools", response_model=ToolSettingsRead)
async def get_other_user_tools(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.tool_settings_service import get_user_tool_settings
    return await get_user_tool_settings(db, target_user)


@router.put("/users/{user_id}/tools", response_model=ToolSettingsRead)
async def update_other_user_tools(
    user_id: int,
    body: ToolSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.tool_settings_service import apply_tool_settings_update
    try:
        return await apply_tool_settings_update(db, target_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tools", response_model=ToolSettingsRead)
async def get_user_tools(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.tool_settings_service import get_user_tool_settings
    from backend.schemas.tool_settings import ToolSettingsRead
    return await get_user_tool_settings(db, current_user)


@router.put("/tools", response_model=ToolSettingsRead)
async def update_user_tools(
    body: ToolSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_tool_settings_permission),
):
    from backend.services.tool_settings_service import apply_tool_settings_update
    from backend.schemas.tool_settings import ToolSettingsRead
    try:
        return await apply_tool_settings_update(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents", response_model=AgentSettingsRead)
async def get_user_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.agent_settings_service import get_user_agent_settings
    return await get_user_agent_settings(db, current_user)


@router.put("/agents", response_model=AgentSettingsRead)
async def update_user_agents(
    body: AgentSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.agent_settings_service import apply_agent_settings_update
    try:
        return await apply_agent_settings_update(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}/agents", response_model=AgentSettingsRead)
async def get_other_user_agents(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.agent_settings_service import get_user_agent_settings
    return await get_user_agent_settings(db, target_user)


@router.put("/users/{user_id}/agents", response_model=AgentSettingsRead)
async def update_other_user_agents(
    user_id: int,
    body: AgentSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.agent_settings_service import apply_agent_settings_update
    try:
        return await apply_agent_settings_update(db, target_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/server", response_model=AgentSettingsRead)
async def get_server_agents(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from backend.services.agent_settings_service import get_server_agent_settings
    return await get_server_agent_settings(db)


@router.put("/agents/server", response_model=AgentSettingsRead)
async def update_server_agents(
    body: AgentSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from backend.services.agent_settings_service import apply_server_agent_settings_update
    try:
        return await apply_server_agent_settings_update(db, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
