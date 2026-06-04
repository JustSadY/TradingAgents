from __future__ import annotations
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.tool_settings import AgentToolSetting
from backend.models.user import User
from backend.trading_agents.agents.tools.registry import registry
from backend.trading_agents.agents.tools.base import BaseAgentTool
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingValue, ToolSettingsUpdate


def validate_field(field: Any, value: Any) -> Any:
    if value is None:
        return field.default

    if field.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Field '{field.key}' must be a boolean.")
        return value

    if field.type == "number":
        if not isinstance(value, (int, float)):
            raise ValueError(f"Field '{field.key}' must be a number.")
        if field.min is not None and value < field.min:
            raise ValueError(f"Field '{field.key}' must be >= {field.min}.")
        if field.max is not None and value > field.max:
            raise ValueError(f"Field '{field.key}' must be <= {field.max}.")
        return value

    if field.type == "string" or field.type == "textarea" or field.type == "secret":
        if not isinstance(value, str):
            raise ValueError(f"Field '{field.key}' must be a string.")
        return value

    if field.type == "string_list":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"Field '{field.key}' must be a list of strings.")
        return value

    if field.type == "select":
        if not isinstance(value, str):
            raise ValueError(f"Field '{field.key}' must be a string.")
        allowed_vals = {opt.value for opt in field.options}
        if allowed_vals and value not in allowed_vals:
            raise ValueError(f"Field '{field.key}' value '{value}' must be one of {allowed_vals}.")
        return value

    if field.type == "multi_select":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"Field '{field.key}' must be a list of strings.")
        allowed_vals = {opt.value for opt in field.options}
        if allowed_vals and any(x not in allowed_vals for x in value):
            raise ValueError(f"Field '{field.key}' values {value} must be sub-elements of {allowed_vals}.")
        return value

    return value


def validate_tool_settings(tool: BaseAgentTool, incoming: dict[str, Any]) -> dict[str, Any]:
    schema_by_key = {field.key: field for field in tool.settings_schema}
    normalized = {}

    for key, value in incoming.items():
        if key not in schema_by_key:
            raise ValueError(f"Unknown setting '{key}' for tool '{tool.key}'.")
        field = schema_by_key[key]
        normalized[key] = validate_field(field, value)

    for field in tool.settings_schema:
        if field.required and field.key not in normalized and field.default is None:
            raise ValueError(f"Missing required setting '{field.key}' for tool '{tool.key}'.")
        if field.key not in normalized:
            normalized[field.key] = field.default

    return normalized


async def get_user_tool_settings(db: AsyncSession, user: User) -> ToolSettingsRead:
    # 1. Fetch DB overrides for this user
    result = await db.execute(
        select(AgentToolSetting)
        .where(AgentToolSetting.scope == "user")
        .where(AgentToolSetting.user_id == user.id)
    )
    user_rows = {row.tool_key: row for row in result.scalars().all()}

    # Also load tool access
    from backend.services.tool_access_service import get_user_tool_access
    tool_access_map = await get_user_tool_access(db, user.id)

    # 2. Build map of all registered tools
    tools_map = {}
    for tool in registry.list():
        if not user.is_admin:
            if not tool_access_map.get(tool.key, {}).get("can_view", True):
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
    result = await db.execute(
        select(AgentToolSetting)
        .where(AgentToolSetting.scope == "server")
        .where(AgentToolSetting.user_id.is_(None))
    )
    server_rows = {row.tool_key: row for row in result.scalars().all()}

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
    result = await db.execute(
        select(AgentToolSetting)
        .where(AgentToolSetting.scope == "user")
        .where(AgentToolSetting.user_id == user.id)
    )
    user_rows = {row.tool_key: row for row in result.scalars().all()}

    # Also load tool access
    from backend.services.tool_access_service import get_user_tool_access
    tool_access_map = await get_user_tool_access(db, user.id)

    for tool_key, update in body.tools.items():
        tool = registry.get(tool_key)
        if not tool:
            raise ValueError(f"Unknown tool key '{tool_key}'.")

        # Validate permissions for non-admin users
        if not user.is_admin:
            perms = tool_access_map.get(tool_key, {})
            if not perms.get("can_view", True):
                raise ValueError(f"You do not have permission to view tool '{tool_key}'.")
            if update.enabled is not None or update.reset_enabled:
                if not perms.get("can_enable", False):
                    raise ValueError(f"You do not have permission to enable/disable tool '{tool_key}'.")
            if update.settings is not None or update.reset_settings:
                if not perms.get("can_edit", False):
                    raise ValueError(f"You do not have permission to modify settings for tool '{tool_key}'.")

        row = user_rows.get(tool_key)
        if not row:
            row = AgentToolSetting(
                scope="user",
                user_id=user.id,
                tool_key=tool_key,
                enabled=tool.default_enabled,
                settings={}
            )
            db.add(row)

        if update.reset_enabled:
            row.enabled = tool.default_enabled
        elif update.enabled is not None:
            row.enabled = update.enabled

        current_settings = row.settings.copy()
        if update.reset_settings:
            default_settings = tool.default_settings(scope="user")
            for k in update.reset_settings:
                if k in current_settings:
                    current_settings[k] = default_settings.get(k)
        elif update.settings is not None:
            validated = validate_tool_settings(tool, update.settings)
            current_settings.update(validated)

        row.settings = current_settings

    await db.flush()
    return await get_user_tool_settings(db, user)


async def apply_server_tool_settings_update(db: AsyncSession, body: ToolSettingsUpdate) -> ToolSettingsRead:
    result = await db.execute(
        select(AgentToolSetting)
        .where(AgentToolSetting.scope == "server")
        .where(AgentToolSetting.user_id.is_(None))
    )
    server_rows = {row.tool_key: row for row in result.scalars().all()}

    for tool_key, update in body.tools.items():
        tool = registry.get(tool_key)
        if not tool:
            raise ValueError(f"Unknown tool key '{tool_key}'.")

        row = server_rows.get(tool_key)
        if not row:
            row = AgentToolSetting(
                scope="server",
                user_id=None,
                tool_key=tool_key,
                enabled=tool.default_enabled,
                settings={}
            )
            db.add(row)

        if update.reset_enabled:
            row.enabled = tool.default_enabled
        elif update.enabled is not None:
            row.enabled = update.enabled

        current_settings = row.settings.copy()
        if update.reset_settings:
            default_settings = tool.default_settings(scope="server")
            for k in update.reset_settings:
                if k in current_settings:
                    current_settings[k] = default_settings.get(k)
        elif update.settings is not None:
            validated = validate_tool_settings(tool, update.settings)
            current_settings.update(validated)

        row.settings = current_settings

    await db.flush()
    return await get_server_tool_settings(db)


def build_tool_runtime_state(tool: BaseAgentTool, server_row: AgentToolSetting | None, user_row: AgentToolSetting | None) -> dict[str, Any]:
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
    result = await db.execute(
        select(AgentToolSetting)
        .where(AgentToolSetting.scope == "server")
        .where(AgentToolSetting.user_id.is_(None))
    )
    server_rows = {row.tool_key: row for row in result.scalars().all()}

    # 2. Load User Tool Settings
    user_rows = {}
    if user_id is not None:
        result = await db.execute(
            select(AgentToolSetting)
            .where(AgentToolSetting.scope == "user")
            .where(AgentToolSetting.user_id == user_id)
        )
        user_rows = {row.tool_key: row for row in result.scalars().all()}

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
        from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess
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
        }
    }
