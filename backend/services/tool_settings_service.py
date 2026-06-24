from __future__ import annotations

from typing import Any

from pydantic import Field as PydanticField
from pydantic import create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import AgentToolSetting, UserAgentAccess, UserToolAccess, UserToolFieldAccess
from backend.models.user import User
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate, ToolSettingValue
from backend.services.tool_access_service import get_user_tool_access
from backend.trading_agents.agents.tools.base import BaseAgentTool
from backend.trading_agents.agents.tools.registry import registry


def _get_pydantic_type(field_type: str) -> Any:
    mapping = {
        "boolean": bool,
        "number": float,
        "string": str,
        "textarea": str,
        "secret": str,
        "string_list": list[str],
        "select": str,
        "multi_select": list[str],
    }
    return mapping.get(field_type, Any)


def validate_tool_settings(tool: BaseAgentTool, incoming: dict[str, Any]) -> dict[str, Any]:
    """Validate incoming settings against the tool's schema using dynamic Pydantic models."""
    fields = {}
    for field in tool.settings_schema:
        f_type = _get_pydantic_type(field.type)
        default = field.default

        # Build field constraints
        extra_kwargs = {}
        if field.type == "number":
            if field.min is not None:
                extra_kwargs["ge"] = field.min
            if field.max is not None:
                extra_kwargs["le"] = field.max

        # For selects, we could add Literal or Validator, but keeping it simple for now
        # with basic type check + manual check if needed.

        fields[field.key] = (f_type, PydanticField(default=default, **extra_kwargs))

    # Create a dynamic Pydantic model for this tool
    ToolModel = create_model(f"Dynamic{tool.key}Model", **fields)

    try:
        validated_obj = ToolModel(**incoming)
        normalized = validated_obj.model_dump()

        # Manual check for selects/options which are harder to do purely with create_model dynamic types
        for field in tool.settings_schema:
            if field.type in ("select", "multi_select") and field.options:
                allowed = {opt.value for opt in field.options}
                val = normalized.get(field.key)
                if field.type == "select" and val not in allowed:
                    raise ValueError(f"Field '{field.key}' value '{val}' must be one of {allowed}.")
                if field.type == "multi_select" and val:
                    if not all(v in allowed for v in val):
                        raise ValueError(f"Field '{field.key}' values {val} must be sub-elements of {allowed}.")

        return normalized
    except Exception as e:
        # Re-wrap Pydantic errors for consistency
        raise ValueError(str(e)) from e


async def _check_tool_availability(db: AsyncSession, user_id: int, tool: BaseAgentTool) -> bool:
    """Helper to check if a tool is available based on the agent hierarchy."""
    if not tool.allowed_analysts:
        return True

    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.agents.hierarchy import AgentHierarchy

    agent_ctx = await build_agent_runtime_context(db, user_id)
    hierarchy = AgentHierarchy(agent_ctx)

    return any(hierarchy.is_enabled(a) for a in tool.allowed_analysts)


async def get_user_tool_settings(db: AsyncSession, user: User) -> ToolSettingsRead:
    # 1. Fetch DB overrides for this user
    from backend.repositories.tool_settings import get_user_tool_settings as _repo_get_user

    user_rows_list = await _repo_get_user(db, user.id)
    user_rows = {row.tool_key: row for row in user_rows_list}

    # Also load tool access
    tool_access_map = await get_user_tool_access(db, user.id)

    # 2. Build map of all registered tools
    tools_map = {}
    for tool in registry.list():
        if not user.is_admin:
            if not tool_access_map.get(tool.key, {}).get("can_view", True):
                continue

        if not await _check_tool_availability(db, user.id, tool):
            continue

        # Get defaults
        default_enabled = tool.default_enabled
        default_settings = tool.default_settings(scope="user")

        row = user_rows.get(tool.key)
        enabled = row.enabled if (row and row.enabled is not None) else default_enabled
        settings = default_settings.copy()
        if row and row.settings:
            settings.update(row.settings)

        tools_map[tool.key] = ToolSettingValue(enabled=enabled, settings=settings)

    return ToolSettingsRead(tools=tools_map)


async def get_server_tool_settings(db: AsyncSession) -> ToolSettingsRead:
    from backend.repositories.tool_settings import get_server_tool_settings as _repo_get_server

    server_rows_list = await _repo_get_server(db)
    server_rows = {row.tool_key: row for row in server_rows_list}

    tools_map = {}
    for tool in registry.list():
        default_enabled = tool.default_enabled
        default_settings = tool.default_settings(scope="server")

        row = server_rows.get(tool.key)
        enabled = row.enabled if (row and row.enabled is not None) else default_enabled
        settings = default_settings.copy()
        if row and row.settings:
            settings.update(row.settings)

        tools_map[tool.key] = ToolSettingValue(enabled=enabled, settings=settings)

    return ToolSettingsRead(tools=tools_map)


async def apply_tool_settings_update(db: AsyncSession, user: User, body: ToolSettingsUpdate) -> ToolSettingsRead:
    # Get existing user rows
    from backend.repositories.tool_settings import get_user_tool_settings as _repo_get_user

    user_rows_list = await _repo_get_user(db, user.id)
    user_rows = {row.tool_key: row for row in user_rows_list}

    # Also load agent settings
    from backend.services.agent_settings_service import build_agent_runtime_context

    agent_ctx = await build_agent_runtime_context(db, user.id)

    for tool_key, update in body.tools.items():
        tool = registry.get(tool_key)
        if not tool:
            raise ValueError(f"Unknown tool key '{tool_key}'.")

        _validate_tool_availability(tool, tool_key, agent_ctx)

        row = user_rows.get(tool_key)
        if not row:
            row = AgentToolSetting(
                scope="user", user_id=user.id, tool_key=tool_key, enabled=tool.default_enabled, settings={}
            )
            db.add(row)

        _apply_tool_setting_row_update(row, update, tool, scope="user")

    await db.flush()
    return await get_user_tool_settings(db, user)


def _validate_tool_availability(tool: BaseAgentTool, tool_key: str, agent_ctx: dict):
    """Raise ValueError if tool is not available due to disabled agents."""
    if tool.allowed_analysts:
        is_any_agent_enabled = any(agent_ctx.get(a, {}).get("enabled", True) for a in tool.allowed_analysts)
        if not is_any_agent_enabled:
            raise ValueError(f"Tool '{tool_key}' is not available because none of its associated agents are enabled.")


def _apply_tool_setting_row_update(row: AgentToolSetting, update: Any, tool: BaseAgentTool, scope: str):
    """Apply enablement and settings updates to an AgentToolSetting row."""
    if update.reset_enabled:
        row.enabled = tool.default_enabled
    elif update.enabled is not None:
        row.enabled = update.enabled

    current_settings = row.settings.copy()
    if update.reset_settings:
        default_settings = tool.default_settings(scope=scope)
        for k in update.reset_settings:
            if k in current_settings:
                current_settings[k] = default_settings.get(k)
    elif update.settings is not None:
        validated = validate_tool_settings(tool, update.settings)
        current_settings.update(validated)

    row.settings = current_settings


async def apply_server_tool_settings_update(db: AsyncSession, body: ToolSettingsUpdate) -> ToolSettingsRead:
    from backend.repositories.tool_settings import get_server_tool_settings as _repo_get_server

    server_rows_list = await _repo_get_server(db)
    server_rows = {row.tool_key: row for row in server_rows_list}

    for tool_key, update in body.tools.items():
        tool = registry.get(tool_key)
        if not tool:
            raise ValueError(f"Unknown tool key '{tool_key}'.")

        row = server_rows.get(tool_key)
        if not row:
            row = AgentToolSetting(
                scope="server", user_id=None, tool_key=tool_key, enabled=tool.default_enabled, settings={}
            )
            db.add(row)

        _apply_tool_setting_row_update(row, update, tool, scope="server")

    await db.flush()
    return await get_server_tool_settings(db)


def build_tool_runtime_state(
    tool: BaseAgentTool, server_row: AgentToolSetting | None, user_row: AgentToolSetting | None
) -> dict[str, Any]:
    server_settings = tool.default_settings(scope="server")
    user_settings = tool.default_settings(scope="user")

    server_enabled = tool.default_enabled
    user_enabled = tool.default_enabled

    if server_row:
        if server_row.enabled is not None:
            server_enabled = server_row.enabled
        server_settings.update(server_row.settings)

    if user_row:
        if user_row.enabled is not None:
            user_enabled = user_row.enabled
        user_settings.update(user_row.settings)

    return {
        "server": {
            "enabled": server_enabled,
            "settings": server_settings,
        },
        "user": {
            "enabled": user_enabled,
            "settings": user_settings,
        },
    }


async def build_global_runtime_context(db: AsyncSession, user_id: int | None) -> dict[str, Any]:
    # 1. Load Server Tool Settings
    from backend.repositories.tool_settings import get_server_tool_settings as _repo_get_server
    from backend.repositories.tool_settings import get_user_tool_settings as _repo_get_user

    server_rows_list = await _repo_get_server(db)
    server_rows = {row.tool_key: row for row in server_rows_list}

    # 2. Load User Tool Settings
    user_rows = {}
    if user_id is not None:
        user_rows_list = await _repo_get_user(db, user_id)
        user_rows = {row.tool_key: row for row in user_rows_list}

    # 3. Build merged active tool settings namespaces
    server_settings_map = {}
    user_settings_map = {}
    for tool in registry.list():
        state = build_tool_runtime_state(tool, server_rows.get(tool.key), user_rows.get(tool.key))
        server_settings_map[tool.key] = state["server"]
        user_settings_map[tool.key] = state["user"]

    # 4. Load access control states
    agent_access = {}
    tool_access = {}
    field_access = {}

    if user_id is not None:
        # Load agent access
        res = await db.execute(select(UserAgentAccess).where(UserAgentAccess.user_id == user_id))
        for row in res.scalars().all():
            agent_access[row.agent_key] = row.can_run

        # Load tool access
        res = await db.execute(select(UserToolAccess).where(UserToolAccess.user_id == user_id))
        for row in res.scalars().all():
            tool_access[row.tool_key] = {
                "can_view": row.can_view,
                "can_use": row.can_use,
                "can_edit": row.can_edit,
                "can_enable": row.can_enable,
            }

        # Load field access
        res = await db.execute(select(UserToolFieldAccess).where(UserToolFieldAccess.user_id == user_id))
        for row in res.scalars().all():
            field_access.setdefault(row.tool_key, {})[row.field_key] = {
                "can_view": row.can_view,
                "can_edit": row.can_edit,
            }

    return {
        "server_settings": server_settings_map,
        "user_settings": user_settings_map,
        "access": {
            "agent_access": agent_access,
            "tool_access": tool_access,
            "field_access": field_access,
        },
    }
