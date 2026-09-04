from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    enforce_setting_section_permission,
    enforce_tool_settings_permission,
    get_current_user,
    require_admin,
)
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.agent_settings import AgentSettingsRead, AgentSettingsUpdate
from backend.schemas.common import OkResponse
from backend.schemas.settings import LLMProviderCatalogEntry, MemoryStatusResponse, SettingsRead, SettingsUpdate
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate
from backend.schemas.webhook import WebhookDeliveryRead, WebhookTestRequest
from backend.services.notification_service import resolve_webhook_target, test_webhook_url
from backend.services.settings_service import (
    SettingsPermissionError,
    apply_settings_update,
    enforce_settings_update_permissions,
    get_or_create_settings,
    settings_to_read,
)
from backend.services.user_service import UserNotFoundError, get_user_or_raise, list_stored_api_key_providers

router = APIRouter(prefix="/api/settings", tags=["settings"])

_USER_NOT_FOUND = "User not found"


async def _require_target_user(db: AsyncSession, user_id: int) -> User:
    try:
        return await get_user_or_raise(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/memory", response_model=MemoryStatusResponse)
async def get_memory_status(
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the user's Mem0 + pgvector long-term-memory status."""
    target_user = current_user
    if user_id is not None and current_user.is_admin:
        target_user = await _require_target_user(db, user_id)

    providers = list_stored_api_key_providers(target_user)
    settings = await get_or_create_settings(db, target_user)
    requested_embedder = (settings.memory_embedder or "openai").strip().lower()
    embedder = "ollama" if requested_embedder == "ollama" else "openai"
    using_openai = embedder == "openai"
    return {
        "enabled": not using_openai or "openai" in providers,
        "store": "mem0-pgvector",
        "embedder": embedder,
        "index": None,
        "embed_model": (
            settings.memory_ollama_embed_model if embedder == "ollama" else settings.memory_openai_embed_model
        ),
        "needs_openai_key": using_openai and "openai" not in providers,
        "agent_qa_enabled": settings.agent_qa_enabled,
    }


@router.get("/llm-catalog", response_model=dict[str, LLMProviderCatalogEntry])
async def get_llm_catalog(_: User = Depends(get_current_user)):
    """Per-provider model dropdown options, sourced from llm_clients/registry.py."""
    from backend.core.catalog import LLM_CATALOG

    return LLM_CATALOG


@router.get("", response_model=SettingsRead)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = await get_or_create_settings(db, current_user)
    return settings_to_read(settings)


async def _apply_settings_update_or_400(
    db: AsyncSession,
    settings,
    body: SettingsUpdate,
):
    """Map service validation failures to the settings API's HTTP contract."""
    try:
        return await apply_settings_update(db, settings, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("", response_model=SettingsRead, responses={403: {"description": "Permission denied"}})
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = await get_or_create_settings(db, current_user)
    if not current_user.is_admin:
        try:
            await enforce_settings_update_permissions(db, current_user, body)
        except SettingsPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
    settings = await _apply_settings_update_or_400(db, settings, body)
    return settings_to_read(settings)


@router.post(
    "/test-webhook",
    response_model=OkResponse,
    responses={400: {"description": "Invalid webhook URL or delivery failed"}},
)
async def test_webhook(
    body: WebhookTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await enforce_setting_section_permission(db, current_user, "webhooks")
    try:
        await resolve_webhook_target(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ok = await test_webhook_url(body.url)
    if not ok:
        raise HTTPException(status_code=400, detail="Webhook delivery failed")
    return {"ok": True}


@router.get("/webhook-deliveries", response_model=list[WebhookDeliveryRead])
async def get_webhook_deliveries(
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = current_user
    if user_id is not None and current_user.is_admin:
        target_user = await _require_target_user(db, user_id)

    from backend.services.settings_service import get_webhook_deliveries as get_webhook_deliveries_svc

    rows = await get_webhook_deliveries_svc(db, target_user.id, 20)
    return [
        WebhookDeliveryRead(
            id=r.id,
            event=r.event,
            url=r.url,
            success=r.success,
            status_code=r.status_code,
            error=r.error,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/users/{user_id}", response_model=SettingsRead, responses={404: {"description": _USER_NOT_FOUND}})
async def get_user_settings_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    settings = await get_or_create_settings(db, target_user)
    return settings_to_read(settings)


@router.put("/users/{user_id}", response_model=SettingsRead, responses={404: {"description": _USER_NOT_FOUND}})
async def update_user_settings_by_id(
    user_id: int,
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    settings = await get_or_create_settings(db, target_user)
    settings = await _apply_settings_update_or_400(db, settings, body)
    return settings_to_read(settings)


@router.get(
    "/users/{user_id}/tools", response_model=ToolSettingsRead, responses={404: {"description": _USER_NOT_FOUND}}
)
async def get_other_user_tools(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.tool_settings_service import get_user_tool_settings

    return await get_user_tool_settings(db, target_user)


@router.put(
    "/users/{user_id}/tools", response_model=ToolSettingsRead, responses={404: {"description": _USER_NOT_FOUND}}
)
async def update_other_user_tools(
    user_id: int,
    body: ToolSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.tool_settings_service import apply_tool_settings_update

    return await apply_tool_settings_update(db, target_user, body)


@router.get("/tools", response_model=ToolSettingsRead)
async def get_user_tools(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.tool_settings_service import get_user_tool_settings

    return await get_user_tool_settings(db, current_user)


@router.put("/tools", response_model=ToolSettingsRead)
async def update_user_tools(
    body: ToolSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await enforce_tool_settings_permission(db, current_user, body)
    from backend.services.tool_settings_service import apply_tool_settings_update

    return await apply_tool_settings_update(db, current_user, body)


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
    await enforce_setting_section_permission(db, current_user, "agents")
    from backend.services.agent_settings_service import apply_agent_settings_update

    return await apply_agent_settings_update(db, current_user, body)


@router.get(
    "/users/{user_id}/agents", response_model=AgentSettingsRead, responses={404: {"description": _USER_NOT_FOUND}}
)
async def get_other_user_agents(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.agent_settings_service import get_user_agent_settings

    return await get_user_agent_settings(db, target_user)


@router.put(
    "/users/{user_id}/agents", response_model=AgentSettingsRead, responses={404: {"description": _USER_NOT_FOUND}}
)
async def update_other_user_agents(
    user_id: int,
    body: AgentSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target_user = await _require_target_user(db, user_id)
    from backend.services.agent_settings_service import apply_server_agent_settings_update

    return await apply_server_agent_settings_update(db, target_user, body)


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

    return await apply_server_agent_settings_update(db, body)
