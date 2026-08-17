from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.tool_access import (
    list_agent_access_rows,
    list_tool_access_rows,
    list_tool_field_access_rows,
    upsert_agent_access,
    upsert_tool_access,
    upsert_tool_field_access,
)
from backend.trading_agents.agents.analyst_registry import list_analysts
from backend.trading_agents.agents.tools.registry import registry


async def get_user_agent_access(db: AsyncSession, user_id: int) -> dict[str, bool]:
    analysts = list_analysts()
    access_map = dict.fromkeys(analysts, True)

    for row in await list_agent_access_rows(db, user_id):
        access_map[row.agent_key] = row.can_run

    return access_map


async def update_user_agent_access(db: AsyncSession, user_id: int, access_map: dict[str, bool]) -> dict[str, bool]:
    analysts = set(list_analysts())
    unknown = sorted(set(access_map) - analysts)
    if unknown:
        raise ValueError(f"Unknown agent keys: {', '.join(unknown)}")

    for agent_key, can_run in access_map.items():
        await upsert_agent_access(db, user_id, agent_key, can_run)

    await db.flush()
    return await get_user_agent_access(db, user_id)


async def get_user_tool_access(db: AsyncSession, user_id: int) -> dict[str, dict]:
    tools = registry.list()
    access_map = {
        tool.key: {
            "can_view": True,
            "can_use": True,
            "can_edit": False,
            "can_enable": False,
        }
        for tool in tools
    }

    for row in await list_tool_access_rows(db, user_id):
        if row.tool_key in access_map:
            access_map[row.tool_key] = {
                "can_view": row.can_view,
                "can_use": row.can_use,
                "can_edit": row.can_edit,
                "can_enable": row.can_enable,
            }

    return access_map


async def update_user_tool_access(db: AsyncSession, user_id: int, updates: dict[str, dict]) -> dict[str, dict]:
    known = {tool.key for tool in registry.list()}
    unknown = sorted(set(updates) - known)
    if unknown:
        raise ValueError(f"Unknown tool keys: {', '.join(unknown)}")

    allowed_perm_keys = {"can_view", "can_use", "can_edit", "can_enable"}
    for tool_key, perms in updates.items():
        extra = sorted(set(perms) - allowed_perm_keys)
        if extra:
            raise ValueError(f"Unknown permissions for {tool_key}: {', '.join(extra)}")
        await upsert_tool_access(db, user_id, tool_key, perms)

    await db.flush()
    return await get_user_tool_access(db, user_id)


async def get_user_tool_field_access(db: AsyncSession, user_id: int) -> dict[str, dict[str, dict]]:
    access_map = {}
    for tool in registry.list():
        access_map[tool.key] = {
            field.key: {
                "can_view": True,
                "can_edit": True,
            }
            for field in tool.settings_schema
        }

    for row in await list_tool_field_access_rows(db, user_id):
        if row.tool_key in access_map and row.field_key in access_map[row.tool_key]:
            access_map[row.tool_key][row.field_key] = {
                "can_view": row.can_view,
                "can_edit": row.can_edit,
            }

    return access_map


async def update_user_tool_field_access(
    db: AsyncSession, user_id: int, updates: dict[str, dict[str, dict]]
) -> dict[str, dict[str, dict]]:
    known_tools = {tool.key for tool in registry.list()}
    unknown_tools = sorted(set(updates) - known_tools)
    if unknown_tools:
        raise ValueError(f"Unknown tool keys: {', '.join(unknown_tools)}")

    for tool_key, fields in updates.items():
        tool = registry.get(tool_key)
        field_keys = {f.key for f in tool.settings_schema}
        unknown_fields = sorted(set(fields) - field_keys)
        if unknown_fields:
            raise ValueError(f"Unknown fields for {tool_key}: {', '.join(unknown_fields)}")

        for field_key, perms in fields.items():
            extra = sorted(set(perms) - {"can_view", "can_edit"})
            if extra:
                raise ValueError(f"Unknown field permissions for {tool_key}.{field_key}: {', '.join(extra)}")
            await upsert_tool_field_access(db, user_id, tool_key, field_key, perms)

    await db.flush()
    return await get_user_tool_field_access(db, user_id)


async def get_user_access_overrides(db: AsyncSession, user_id: int) -> dict[str, dict]:
    """Return only persisted access overrides for runtime-context assembly."""
    agent_access = {row.agent_key: row.can_run for row in await list_agent_access_rows(db, user_id)}

    tool_access = {
        row.tool_key: {
            "can_view": row.can_view,
            "can_use": row.can_use,
            "can_edit": row.can_edit,
            "can_enable": row.can_enable,
        }
        for row in await list_tool_access_rows(db, user_id)
    }

    field_access: dict[str, dict[str, dict[str, bool]]] = {}
    for row in await list_tool_field_access_rows(db, user_id):
        field_access.setdefault(row.tool_key, {})[row.field_key] = {
            "can_view": row.can_view,
            "can_edit": row.can_edit,
        }

    return {
        "agent_access": agent_access,
        "tool_access": tool_access,
        "field_access": field_access,
    }
