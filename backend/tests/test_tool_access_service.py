"""Tests for per-user agent/tool/field permission resolution
(``tool_access_service``)."""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.tool_settings import UserAgentAccess, UserToolAccess  # noqa: F401 — register tables
from backend.models.user import User
from backend.services import tool_access_service as svc


class FakeRegistry:
    def __init__(self, tools):
        self._tools = {t.key: t for t in tools}

    def list(self):
        return list(self._tools.values())

    def get(self, key):
        return self._tools.get(key)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user_id(db):
    u = User(username="alice", hashed_password="x", role="user")
    db.add(u)
    await db.flush()
    return u.id


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    field = SimpleNamespace(key="limit")
    tools = [
        SimpleNamespace(key="news_tool", settings_schema=[field]),
        SimpleNamespace(key="chart_tool", settings_schema=[]),
    ]
    monkeypatch.setattr(svc, "registry", FakeRegistry(tools))
    monkeypatch.setattr(svc, "list_analysts", lambda: ["market", "social"])


# ---------------------------------------------------------------------------
# Agent access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_access_defaults_to_all_allowed(db, user_id):
    assert await svc.get_user_agent_access(db, user_id) == {"market": True, "social": True}


@pytest.mark.asyncio
async def test_agent_access_db_rows_override_defaults(db, user_id):
    db.add(UserAgentAccess(user_id=user_id, agent_key="social", can_run=False))
    await db.flush()
    assert await svc.get_user_agent_access(db, user_id) == {"market": True, "social": False}


@pytest.mark.asyncio
async def test_update_agent_access_ignores_unknown_agents(db, user_id):
    result = await svc.update_user_agent_access(db, user_id, {"social": False, "made_up_agent": False})
    assert result == {"market": True, "social": False}
    assert "made_up_agent" not in result


@pytest.mark.asyncio
async def test_update_agent_access_flips_existing_row(db, user_id):
    await svc.update_user_agent_access(db, user_id, {"social": False})
    result = await svc.update_user_agent_access(db, user_id, {"social": True})
    assert result["social"] is True


@pytest.mark.asyncio
async def test_agent_access_is_per_user(db, user_id):
    other = User(username="bob", hashed_password="x", role="user")
    db.add(other)
    await db.flush()

    await svc.update_user_agent_access(db, user_id, {"social": False})
    assert (await svc.get_user_agent_access(db, other.id))["social"] is True


# ---------------------------------------------------------------------------
# Tool access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_access_defaults_view_use_only(db, user_id):
    access = await svc.get_user_tool_access(db, user_id)
    assert access["news_tool"] == {"can_view": True, "can_use": True, "can_edit": False, "can_enable": False}
    assert set(access) == {"news_tool", "chart_tool"}


@pytest.mark.asyncio
async def test_stale_db_rows_for_unregistered_tools_are_ignored(db, user_id):
    db.add(UserToolAccess(user_id=user_id, tool_key="removed_tool", can_view=False))
    await db.flush()
    access = await svc.get_user_tool_access(db, user_id)
    assert "removed_tool" not in access


@pytest.mark.asyncio
async def test_update_tool_access_partial_perms_touch_only_named_flags(db, user_id):
    await svc.update_user_tool_access(db, user_id, {"news_tool": {"can_view": False}})
    access = await svc.update_user_tool_access(db, user_id, {"news_tool": {"can_edit": True}})
    # can_view from the earlier update must survive the partial edit.
    assert access["news_tool"] == {"can_view": False, "can_use": True, "can_edit": True, "can_enable": False}


@pytest.mark.asyncio
async def test_update_tool_access_skips_unknown_tools(db, user_id):
    access = await svc.update_user_tool_access(db, user_id, {"made_up_tool": {"can_view": False}})
    assert "made_up_tool" not in access


# ---------------------------------------------------------------------------
# Field-level access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_field_access_defaults_from_settings_schema(db, user_id):
    access = await svc.get_user_tool_field_access(db, user_id)
    assert access["news_tool"] == {"limit": {"can_view": True, "can_edit": True}}
    assert access["chart_tool"] == {}


@pytest.mark.asyncio
async def test_update_field_access_only_known_fields(db, user_id):
    access = await svc.update_user_tool_field_access(
        db,
        user_id,
        {"news_tool": {"limit": {"can_edit": False}, "ghost_field": {"can_view": False}}},
    )
    assert access["news_tool"]["limit"] == {"can_view": True, "can_edit": False}
    assert "ghost_field" not in access["news_tool"]
