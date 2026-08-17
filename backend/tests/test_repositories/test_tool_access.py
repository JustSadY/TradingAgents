from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories.tool_access import (
    list_agent_access_rows,
    list_tool_access_rows,
    list_tool_field_access_rows,
    upsert_agent_access,
    upsert_tool_access,
    upsert_tool_field_access,
)


async def test_agent_access_upsert_updates_existing_row(
    db: AsyncSession,
    test_user: User,
) -> None:
    await upsert_agent_access(db, test_user.id, "fundamentals", False)
    await db.flush()

    rows = await list_agent_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].agent_key == "fundamentals"
    assert rows[0].can_run is False

    await upsert_agent_access(db, test_user.id, "fundamentals", True)
    await db.flush()

    rows = await list_agent_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].can_run is True


async def test_tool_access_upsert_preserves_unspecified_permissions(
    db: AsyncSession,
    test_user: User,
) -> None:
    await upsert_tool_access(db, test_user.id, "search_web", {"can_view": False})
    await db.flush()

    rows = await list_tool_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].can_view is False
    assert rows[0].can_use is True
    assert rows[0].can_edit is False
    assert rows[0].can_enable is False

    await upsert_tool_access(db, test_user.id, "search_web", {"can_edit": True})
    await db.flush()

    rows = await list_tool_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].can_view is False
    assert rows[0].can_edit is True


async def test_tool_field_access_upsert_updates_existing_row(
    db: AsyncSession,
    test_user: User,
) -> None:
    await upsert_tool_field_access(
        db,
        test_user.id,
        "search_web",
        "searxng_url",
        {"can_view": False, "can_edit": False},
    )
    await db.flush()

    rows = await list_tool_field_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].can_view is False
    assert rows[0].can_edit is False

    await upsert_tool_field_access(
        db,
        test_user.id,
        "search_web",
        "searxng_url",
        {"can_edit": True},
    )
    await db.flush()

    rows = await list_tool_field_access_rows(db, test_user.id)
    assert len(rows) == 1
    assert rows[0].can_view is False
    assert rows[0].can_edit is True
