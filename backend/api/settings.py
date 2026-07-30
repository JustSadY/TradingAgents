from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    enforce_setting_section_permission,
    enforce_tool_settings_permission,
    get_current_user,
    require_admin,
)
from backend.core.database import get_db
from backend.models.user import User
from backend.repositories.permissions import list_allowed_setting_sections
from backend.repositories.users import get_user_by_id
from backend.schemas.agent_settings import AgentSettingsRead, AgentSettingsUpdate
from backend.schemas.common import OkResponse
from backend.schemas.settings import LLMProviderCatalogEntry, MemoryStatusResponse, SettingsRead, SettingsUpdate
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate
from backend.schemas.webhook import WebhookDeliveryRead
from backend.services.notification_service import test_webhook_url, validate_webhook_url
from backend.services.settings_service import (
    apply_settings_update,
    get_or_create_settings,
    settings_to_read,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_USER_NOT_FOUND = "User not found"


@router.get("/memory", response_model=MemoryStatusResponse)
async def get_memory_status(
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The calling user's own vector-memory status (everything is per-user)."""
    from backend.core.config import get_settings as _cfg
    from backend.services.user_service import list_user_api_key_providers

    target_user = current_user
    if user_id is not None and current_user.is_admin:
        target_user = await get_user_by_id(db, user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

    fernet = _cfg().get_fernet()
    providers = list_user_api_key_providers(target_user, fernet)
    settings = await get_or_create_settings(db, target_user)
    store_kind = getattr(settings, "memory_store", None) or "pinecone"
    using_openai = store_kind == "pgvector" or settings.memory_embedder == "openai"
    return {
        "enabled": "openai" in providers if store_kind == "pgvector" else "pinecone" in providers,
        "store": store_kind,
        "embedder": "openai" if store_kind == "pgvector" else settings.memory_embedder,
        "index": settings.pinecone_index,
        "embed_model": settings.memory_openai_embed_model if using_openai else settings.pinecone_embed_model,
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


async def _check_section_permissions(db: AsyncSession, user: User, body: SettingsUpdate) -> None:
    """Non-admins may only edit settings sections explicitly granted to them, and
    never advanced engine settings."""
    from backend.models.page_permission import SECTION_FIELDS

    allowed_sections = await list_allowed_setting_sections(db, user.id)
    attempted = body.model_dump(exclude_unset=True)
    advanced_fields = {"max_recur_limit"}
    if any(f in attempted for f in advanced_fields):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Advanced engine settings can only be modified by administrators.",
        )

    mapped_fields = {field for fields in SECTION_FIELDS.values() for field in fields}
    unmapped = set(attempted) - mapped_fields
    if unmapped:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No permission section is configured for settings: {', '.join(sorted(unmapped))}",
        )
    for section, fields in SECTION_FIELDS.items():
        if any(f in attempted for f in fields) and section not in allowed_sections:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to modify settings in section: {section}",
            )


async def _validate_webhook_url_if_present(body: SettingsUpdate) -> None:
    """Reject webhook URLs that resolve to a private/internal address.

    The Pydantic field validator only checks the URL is well-formed http(s);
    it can't do the DNS resolution needed to catch SSRF targets (localhost,
    169.254.169.254, RFC1918 ranges, ...). This is the actual save path, so it
    must run the same check that /api/settings/test-webhook already does —
    otherwise that endpoint's guard is easily bypassed by saving directly.
    """
    url = body.model_dump(exclude_unset=True).get("webhook_url")
    if url:
        try:
            await validate_webhook_url(url)
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
        await _check_section_permissions(db, current_user, body)
    await _validate_webhook_url_if_present(body)
    settings = await apply_settings_update(db, settings, body)
    return settings_to_read(settings)


class WebhookTestRequest(BaseModel):
    url: str


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
        await validate_webhook_url(body.url)
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
        target_user = await get_user_by_id(db, user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)

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


async def _require_target_user(db: AsyncSession, user_id: int) -> User:
    target_user = await get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    return target_user


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
    await _validate_webhook_url_if_present(body)
    settings = await apply_settings_update(db, settings, body)
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
    from backend.services.agent_settings_service import apply_agent_settings_update

    return await apply_agent_settings_update(db, target_user, body)


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
