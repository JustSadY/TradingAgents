from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.models.user import User


class TestSettingsAPI:
    async def test_get_settings(self, auth_client: AsyncClient, db: AsyncSession, test_user: User):
        settings = AppSettings(user_id=test_user.id, llm_provider="openai", llm_model="gpt-4o-mini")
        db.add(settings)
        await db.flush()

        resp = await auth_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_provider" in data
        assert data["llm_provider"] == "openai"

    async def test_update_settings(self, auth_client: AsyncClient, db: AsyncSession, test_user: User):
        settings = AppSettings(user_id=test_user.id, llm_provider="openai", llm_model="gpt-4o-mini")
        db.add(settings)
        await db.flush()

        resp = await auth_client.put("/api/settings", json={"llm_provider": "anthropic", "llm_model": "claude-3-opus"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "anthropic"
        assert data["llm_model"] == "claude-3-opus"

    async def test_get_settings_unauthorized(self, async_client: AsyncClient):
        resp = await async_client.get("/api/settings")
        assert resp.status_code == 401

    async def test_get_meta(self, async_client: AsyncClient):
        resp = await async_client.get("/api/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert "investor_personas" in data
        assert "tool_categories" in data

    async def test_get_llm_catalog(self, async_client: AsyncClient):
        resp = await async_client.get("/api/settings/llm-catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
