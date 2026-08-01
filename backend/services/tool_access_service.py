from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess
from backend.trading_agents.agents.analyst_registry import list_analysts
from backend.trading_agents.agents.tools.registry import registry

async def get_user_agent_access(db: AsyncSession, user_id: int) -> dict[str, bool]:
    analysts = list_analysts()
    access_map = dict.fromkeys(analysts, True)

    result = await db.execute(select(UserAgentAccess).where(UserAgentAccess.user_id == user_id))
    for row in result.scalars().all():
        access_map[row.agent_key] = row.can_run

    return access_map

async def update_user_agent_access(db: AsyncSession, user_id: int, access_map: dict[str, bool]) -> dict[str, bool]:
    analysts = set(list_analysts())
    for agent_key, can_run in access_map.items():
        if agent_key not in analysts:
            continue
        result = await db.execute(
            select(UserAgentAccess)
            .where(UserAgentAccess.user_id == user_id)
            .where(UserAgentAccess.agent_key == agent_key)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = UserAgentAccess(user_id=user_id, agent_key=agent_key, can_run=can_run)
            db.add(row)
        else:
            row.can_run = can_run

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

    result = await db.execute(select(UserToolAccess).where(UserToolAccess.user_id == user_id))
    for row in result.scalars().all():
        if row.tool_key in access_map:
            access_map[row.tool_key] = {
                "can_view": row.can_view,
                "can_use": row.can_use,
                "can_edit": row.can_edit,
                "can_enable": row.can_enable,
            }

    return access_map

async def update_user_tool_access(db: AsyncSession, user_id: int, updates: dict[str, dict]) -> dict[str, dict]:
    for tool_key, perms in updates.items():
        if not registry.get(tool_key):
            continue
        result = await db.execute(
            select(UserToolAccess).where(UserToolAccess.user_id == user_id).where(UserToolAccess.tool_key == tool_key)
        )
        row = result.scalar_one_or_none()
        if row is None:
            _add_user_tool_access(db, user_id, tool_key, perms)
        else:
            _apply_tool_access_perms(row, perms)

    await db.flush()
    return await get_user_tool_access(db, user_id)

def _add_user_tool_access(db: AsyncSession, user_id: int, tool_key: str, perms: dict):
    row = UserToolAccess(
        user_id=user_id,
        tool_key=tool_key,
        can_view=perms.get("can_view", True),
        can_use=perms.get("can_use", True),
        can_edit=perms.get("can_edit", False),
        can_enable=perms.get("can_enable", False),
    )
    db.add(row)

def _apply_tool_access_perms(row: UserToolAccess, perms: dict):
    for key in ("can_view", "can_use", "can_edit", "can_enable"):
        if key in perms:
            setattr(row, key, perms[key])

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

    result = await db.execute(select(UserToolFieldAccess).where(UserToolFieldAccess.user_id == user_id))
    for row in result.scalars().all():
        if row.tool_key in access_map and row.field_key in access_map[row.tool_key]:
            access_map[row.tool_key][row.field_key] = {
                "can_view": row.can_view,
                "can_edit": row.can_edit,
            }

    return access_map

async def update_user_tool_field_access(
    db: AsyncSession, user_id: int, updates: dict[str, dict[str, dict]]
) -> dict[str, dict[str, dict]]:
    for tool_key, fields in updates.items():
        tool = registry.get(tool_key)
        if not tool:
            continue
        field_keys = {f.key for f in tool.settings_schema}

        for field_key, perms in fields.items():
            if field_key not in field_keys:
                continue
            result = await db.execute(
                select(UserToolFieldAccess)
                .where(UserToolFieldAccess.user_id == user_id)
                .where(UserToolFieldAccess.tool_key == tool_key)
                .where(UserToolFieldAccess.field_key == field_key)
            )
            row = result.scalar_one_or_none()
            if row is None:
                _add_user_tool_field_access(db, user_id, tool_key, field_key, perms)
            else:
                _apply_field_access_perms(row, perms)

    await db.flush()
    return await get_user_tool_field_access(db, user_id)

def _add_user_tool_field_access(db: AsyncSession, user_id: int, tool_key: str, field_key: str, perms: dict):
    row = UserToolFieldAccess(
        user_id=user_id,
        tool_key=tool_key,
        field_key=field_key,
        can_view=perms.get("can_view", True),
        can_edit=perms.get("can_edit", True),
    )
    db.add(row)

def _apply_field_access_perms(row: UserToolFieldAccess, perms: dict):
    if "can_view" in perms:
        row.can_view = perms["can_view"]
    if "can_edit" in perms:
        row.can_edit = perms["can_edit"]
