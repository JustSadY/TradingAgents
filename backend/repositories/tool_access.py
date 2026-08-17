from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess


async def list_agent_access_rows(db: AsyncSession, user_id: int) -> list[UserAgentAccess]:
    result = await db.execute(select(UserAgentAccess).where(UserAgentAccess.user_id == user_id))
    return list(result.scalars().all())


async def upsert_agent_access(db: AsyncSession, user_id: int, agent_key: str, can_run: bool) -> None:
    result = await db.execute(
        select(UserAgentAccess)
        .where(UserAgentAccess.user_id == user_id)
        .where(UserAgentAccess.agent_key == agent_key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(UserAgentAccess(user_id=user_id, agent_key=agent_key, can_run=can_run))
    else:
        row.can_run = can_run


async def list_tool_access_rows(db: AsyncSession, user_id: int) -> list[UserToolAccess]:
    result = await db.execute(select(UserToolAccess).where(UserToolAccess.user_id == user_id))
    return list(result.scalars().all())


async def upsert_tool_access(db: AsyncSession, user_id: int, tool_key: str, perms: dict[str, bool]) -> None:
    result = await db.execute(
        select(UserToolAccess).where(UserToolAccess.user_id == user_id).where(UserToolAccess.tool_key == tool_key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(
            UserToolAccess(
                user_id=user_id,
                tool_key=tool_key,
                can_view=perms.get("can_view", True),
                can_use=perms.get("can_use", True),
                can_edit=perms.get("can_edit", False),
                can_enable=perms.get("can_enable", False),
            )
        )
        return

    for key in ("can_view", "can_use", "can_edit", "can_enable"):
        if key in perms:
            setattr(row, key, perms[key])


async def list_tool_field_access_rows(db: AsyncSession, user_id: int) -> list[UserToolFieldAccess]:
    result = await db.execute(select(UserToolFieldAccess).where(UserToolFieldAccess.user_id == user_id))
    return list(result.scalars().all())


async def upsert_tool_field_access(
    db: AsyncSession,
    user_id: int,
    tool_key: str,
    field_key: str,
    perms: dict[str, bool],
) -> None:
    result = await db.execute(
        select(UserToolFieldAccess)
        .where(UserToolFieldAccess.user_id == user_id)
        .where(UserToolFieldAccess.tool_key == tool_key)
        .where(UserToolFieldAccess.field_key == field_key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(
            UserToolFieldAccess(
                user_id=user_id,
                tool_key=tool_key,
                field_key=field_key,
                can_view=perms.get("can_view", True),
                can_edit=perms.get("can_edit", True),
            )
        )
        return

    if "can_view" in perms:
        row.can_view = perms["can_view"]
    if "can_edit" in perms:
        row.can_edit = perms["can_edit"]
