from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.services.tool_access_service import (
    update_user_agent_access,
    update_user_tool_access,
    update_user_tool_field_access,
)


async def test_unknown_agent_key_is_rejected_before_persistence(
    db: AsyncSession,
    test_user: User,
) -> None:
    with pytest.raises(ValueError, match="Unknown agent keys"):
        await update_user_agent_access(db, test_user.id, {"__retired_agent__": False})


async def test_unknown_tool_key_is_rejected_before_persistence(
    db: AsyncSession,
    test_user: User,
) -> None:
    with pytest.raises(ValueError, match="Unknown tool keys"):
        await update_user_tool_access(db, test_user.id, {"__retired_tool__": {"can_view": False}})


async def test_unknown_tool_field_key_is_rejected_before_persistence(
    db: AsyncSession,
    test_user: User,
) -> None:
    with pytest.raises(ValueError, match="Unknown tool keys"):
        await update_user_tool_field_access(db, test_user.id, {"__retired_tool__": {"field": {"can_view": False}}})


def test_tool_access_service_does_not_own_sql_or_orm_models() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "tool_access_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "backend.models.tool_settings" not in source
    assert "select(UserAgentAccess" not in source
    assert "select(UserToolAccess" not in source
    assert "select(UserToolFieldAccess" not in source
    assert "backend.repositories.tool_access" in source
