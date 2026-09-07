from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess
from backend.repositories.tool_access import (
    ensure_agent_access_row,
    ensure_tool_access_row,
    ensure_tool_field_access_row,
    list_access_override_rows,
    list_agent_access_rows,
    list_tool_access_rows,
    list_tool_field_access_rows,
)
from backend.trading_agents.agents.analyst_registry import list_analysts
from backend.trading_agents.agents.tools.registry import registry

_TOOL_ACCESS_DEFAULTS = {
    "can_view": True,
    "can_use": True,
    "can_edit": False,
    "can_enable": False,
}
_FIELD_ACCESS_DEFAULTS = {
    "can_view": True,
    "can_edit": True,
}


def _agent_access_map(rows: Iterable[UserAgentAccess]) -> dict[str, bool]:
    access_map = dict.fromkeys(list_analysts(), True)
    for row in rows:
        access_map[row.agent_key] = row.can_run
    return access_map


async def get_user_agent_access(db: AsyncSession, user_id: int) -> dict[str, bool]:
    return _agent_access_map(await list_agent_access_rows(db, user_id))


async def update_user_agent_access(db: AsyncSession, user_id: int, access_map: dict[str, bool]) -> dict[str, bool]:
    analysts = set(list_analysts())
    unknown = sorted(set(access_map) - analysts)
    if unknown:
        raise ValueError(f"Unknown agent keys: {', '.join(unknown)}")

    rows = {row.agent_key: row for row in await list_agent_access_rows(db, user_id)}
    dirty = False
    for agent_key, can_run in access_map.items():
        row = rows.get(agent_key)
        if row is None and can_run is True:
            continue
        if row is not None and row.can_run == can_run:
            continue
        row = ensure_agent_access_row(db, row=row, user_id=user_id, agent_key=agent_key)
        row.can_run = can_run
        rows[agent_key] = row
        dirty = True

    if dirty:
        await db.flush()
    return _agent_access_map(rows.values())


def _tool_access_map(rows: Iterable[UserToolAccess]) -> dict[str, dict[str, bool]]:
    access_map = {tool.key: dict(_TOOL_ACCESS_DEFAULTS) for tool in registry.list()}
    for row in rows:
        if row.tool_key in access_map:
            access_map[row.tool_key] = {
                "can_view": row.can_view,
                "can_use": row.can_use,
                "can_edit": row.can_edit,
                "can_enable": row.can_enable,
            }
    return access_map


async def get_user_tool_access(db: AsyncSession, user_id: int) -> dict[str, dict]:
    return _tool_access_map(await list_tool_access_rows(db, user_id))


async def update_user_tool_access(db: AsyncSession, user_id: int, updates: dict[str, dict]) -> dict[str, dict]:
    known = {tool.key for tool in registry.list()}
    unknown = sorted(set(updates) - known)
    if unknown:
        raise ValueError(f"Unknown tool keys: {', '.join(unknown)}")

    allowed_perm_keys = set(_TOOL_ACCESS_DEFAULTS)
    for tool_key, perms in updates.items():
        extra = sorted(set(perms) - allowed_perm_keys)
        if extra:
            raise ValueError(f"Unknown permissions for {tool_key}: {', '.join(extra)}")

    rows = {row.tool_key: row for row in await list_tool_access_rows(db, user_id)}
    dirty = False
    for tool_key, perms in updates.items():
        row = rows.get(tool_key)
        current = (
            {
                "can_view": row.can_view,
                "can_use": row.can_use,
                "can_edit": row.can_edit,
                "can_enable": row.can_enable,
            }
            if row is not None
            else dict(_TOOL_ACCESS_DEFAULTS)
        )
        desired = {**current, **perms}
        if row is None and desired == _TOOL_ACCESS_DEFAULTS:
            continue
        if row is not None and desired == current:
            continue

        row = ensure_tool_access_row(db, row=row, user_id=user_id, tool_key=tool_key)
        for key, value in desired.items():
            setattr(row, key, value)
        rows[tool_key] = row
        dirty = True

    if dirty:
        await db.flush()
    return _tool_access_map(rows.values())


def _tool_field_access_map(rows: Iterable[UserToolFieldAccess]) -> dict[str, dict[str, dict[str, bool]]]:
    access_map = {
        tool.key: {field.key: dict(_FIELD_ACCESS_DEFAULTS) for field in tool.settings_schema}
        for tool in registry.list()
    }
    for row in rows:
        if row.tool_key in access_map and row.field_key in access_map[row.tool_key]:
            access_map[row.tool_key][row.field_key] = {
                "can_view": row.can_view,
                "can_edit": row.can_edit,
            }
    return access_map


async def get_user_tool_field_access(db: AsyncSession, user_id: int) -> dict[str, dict[str, dict]]:
    return _tool_field_access_map(await list_tool_field_access_rows(db, user_id))


async def update_user_tool_field_access(
    db: AsyncSession, user_id: int, updates: dict[str, dict[str, dict]]
) -> dict[str, dict[str, dict]]:
    known_tools = {tool.key for tool in registry.list()}
    unknown_tools = sorted(set(updates) - known_tools)
    if unknown_tools:
        raise ValueError(f"Unknown tool keys: {', '.join(unknown_tools)}")

    allowed_perm_keys = set(_FIELD_ACCESS_DEFAULTS)
    for tool_key, fields in updates.items():
        tool = registry.get(tool_key)
        field_keys = {f.key for f in tool.settings_schema}
        unknown_fields = sorted(set(fields) - field_keys)
        if unknown_fields:
            raise ValueError(f"Unknown fields for {tool_key}: {', '.join(unknown_fields)}")
        for field_key, perms in fields.items():
            extra = sorted(set(perms) - allowed_perm_keys)
            if extra:
                raise ValueError(f"Unknown field permissions for {tool_key}.{field_key}: {', '.join(extra)}")

    rows = {
        (row.tool_key, row.field_key): row
        for row in await list_tool_field_access_rows(db, user_id)
    }
    dirty = False
    for tool_key, fields in updates.items():
        for field_key, perms in fields.items():
            row_key = (tool_key, field_key)
            row = rows.get(row_key)
            current = (
                {"can_view": row.can_view, "can_edit": row.can_edit}
                if row is not None
                else dict(_FIELD_ACCESS_DEFAULTS)
            )
            desired = {**current, **perms}
            if row is None and desired == _FIELD_ACCESS_DEFAULTS:
                continue
            if row is not None and desired == current:
                continue

            row = ensure_tool_field_access_row(
                db,
                row=row,
                user_id=user_id,
                tool_key=tool_key,
                field_key=field_key,
            )
            row.can_view = desired["can_view"]
            row.can_edit = desired["can_edit"]
            rows[row_key] = row
            dirty = True

    if dirty:
        await db.flush()
    return _tool_field_access_map(rows.values())


async def get_user_access_overrides(db: AsyncSession, user_id: int) -> dict[str, dict]:
    """Return only persisted access overrides for runtime-context assembly."""
    agent_access: dict[str, bool] = {}
    tool_access: dict[str, dict[str, bool]] = {}
    field_access: dict[str, dict[str, dict[str, bool]]] = {}

    for row in await list_access_override_rows(db, user_id):
        kind = row["kind"]
        key = row["key"]
        if kind == "agent":
            agent_access[key] = bool(row["can_view"])
        elif kind == "tool":
            tool_access[key] = {
                "can_view": bool(row["can_view"]),
                "can_use": bool(row["can_use"]),
                "can_edit": bool(row["can_edit"]),
                "can_enable": bool(row["can_enable"]),
            }
        elif kind == "field":
            field_key = row["field_key"]
            if field_key:
                field_access.setdefault(key, {})[field_key] = {
                    "can_view": bool(row["can_view"]),
                    "can_edit": bool(row["can_edit"]),
                }

    return {
        "agent_access": agent_access,
        "tool_access": tool_access,
        "field_access": field_access,
    }
