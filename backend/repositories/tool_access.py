from __future__ import annotations

from sqlalchemy import Boolean, String, cast, literal, null, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess


async def list_agent_access_rows(db: AsyncSession, user_id: int) -> list[UserAgentAccess]:
    result = await db.execute(select(UserAgentAccess).where(UserAgentAccess.user_id == user_id))
    return list(result.scalars().all())


def ensure_agent_access_row(
    db: AsyncSession,
    *,
    row: UserAgentAccess | None,
    user_id: int,
    agent_key: str,
) -> UserAgentAccess:
    if row is not None:
        return row
    row = UserAgentAccess(user_id=user_id, agent_key=agent_key, can_run=True)
    db.add(row)
    return row


async def upsert_agent_access(db: AsyncSession, user_id: int, agent_key: str, can_run: bool) -> None:
    result = await db.execute(
        select(UserAgentAccess)
        .where(UserAgentAccess.user_id == user_id)
        .where(UserAgentAccess.agent_key == agent_key)
    )
    row = ensure_agent_access_row(
        db,
        row=result.scalar_one_or_none(),
        user_id=user_id,
        agent_key=agent_key,
    )
    row.can_run = can_run


async def list_tool_access_rows(db: AsyncSession, user_id: int) -> list[UserToolAccess]:
    result = await db.execute(select(UserToolAccess).where(UserToolAccess.user_id == user_id))
    return list(result.scalars().all())


def ensure_tool_access_row(
    db: AsyncSession,
    *,
    row: UserToolAccess | None,
    user_id: int,
    tool_key: str,
) -> UserToolAccess:
    if row is not None:
        return row
    row = UserToolAccess(
        user_id=user_id,
        tool_key=tool_key,
        can_view=True,
        can_use=True,
        can_edit=False,
        can_enable=False,
    )
    db.add(row)
    return row


async def upsert_tool_access(db: AsyncSession, user_id: int, tool_key: str, perms: dict[str, bool]) -> None:
    result = await db.execute(
        select(UserToolAccess).where(UserToolAccess.user_id == user_id).where(UserToolAccess.tool_key == tool_key)
    )
    row = ensure_tool_access_row(
        db,
        row=result.scalar_one_or_none(),
        user_id=user_id,
        tool_key=tool_key,
    )
    for key in ("can_view", "can_use", "can_edit", "can_enable"):
        if key in perms:
            setattr(row, key, perms[key])


async def list_tool_field_access_rows(db: AsyncSession, user_id: int) -> list[UserToolFieldAccess]:
    result = await db.execute(select(UserToolFieldAccess).where(UserToolFieldAccess.user_id == user_id))
    return list(result.scalars().all())


def ensure_tool_field_access_row(
    db: AsyncSession,
    *,
    row: UserToolFieldAccess | None,
    user_id: int,
    tool_key: str,
    field_key: str,
) -> UserToolFieldAccess:
    if row is not None:
        return row
    row = UserToolFieldAccess(
        user_id=user_id,
        tool_key=tool_key,
        field_key=field_key,
        can_view=True,
        can_edit=True,
    )
    db.add(row)
    return row


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
    row = ensure_tool_field_access_row(
        db,
        row=result.scalar_one_or_none(),
        user_id=user_id,
        tool_key=tool_key,
        field_key=field_key,
    )
    if "can_view" in perms:
        row.can_view = perms["can_view"]
    if "can_edit" in perms:
        row.can_edit = perms["can_edit"]


async def list_access_override_rows(db: AsyncSession, user_id: int) -> list[dict]:
    """Return agent/tool/field overrides with one database round trip.

    Runtime graph setup needs all three override tables together. A discriminated
    ``UNION ALL`` keeps the existing normalized schema while avoiding three
    sequential SELECTs on every analysis start.
    """
    null_string = cast(null(), String)
    null_bool = cast(null(), Boolean)

    agent_rows = select(
        literal("agent").label("kind"),
        UserAgentAccess.agent_key.label("key"),
        null_string.label("field_key"),
        UserAgentAccess.can_run.label("can_view"),
        null_bool.label("can_use"),
        null_bool.label("can_edit"),
        null_bool.label("can_enable"),
    ).where(UserAgentAccess.user_id == user_id)

    tool_rows = select(
        literal("tool").label("kind"),
        UserToolAccess.tool_key.label("key"),
        null_string.label("field_key"),
        UserToolAccess.can_view.label("can_view"),
        UserToolAccess.can_use.label("can_use"),
        UserToolAccess.can_edit.label("can_edit"),
        UserToolAccess.can_enable.label("can_enable"),
    ).where(UserToolAccess.user_id == user_id)

    field_rows = select(
        literal("field").label("kind"),
        UserToolFieldAccess.tool_key.label("key"),
        UserToolFieldAccess.field_key.label("field_key"),
        UserToolFieldAccess.can_view.label("can_view"),
        null_bool.label("can_use"),
        UserToolFieldAccess.can_edit.label("can_edit"),
        null_bool.label("can_enable"),
    ).where(UserToolFieldAccess.user_id == user_id)

    result = await db.execute(union_all(agent_rows, tool_rows, field_rows))
    return [dict(row) for row in result.mappings().all()]
