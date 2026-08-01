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

    async def test_auto_execution_requires_explicit_settings_opt_in(self, auth_client: AsyncClient):
        initial = await auth_client.get("/api/settings")
        assert initial.status_code == 200
        assert initial.json()["auto_execute_signals"] is False

        updated = await auth_client.put("/api/settings", json={"auto_execute_signals": True})
        assert updated.status_code == 200
        assert updated.json()["auto_execute_signals"] is True

    async def test_update_settings_uses_native_webhook_and_fallback_collections(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/api/settings",
            json={
                "webhook_events": ["analysis_complete", "trade_executed"],
                "fallback_llm_chain": [
                    {"provider": " NVIDIA ", "model": " nvidia/nemotron "},
                    {"provider": "openai", "model": "gpt-4o-mini"},
                ],
            },
        )

        assert resp.status_code == 200
        assert resp.json()["webhook_events"] == ["analysis_complete", "trade_executed"]
        assert resp.json()["fallback_llm_chain"] == [
            {"provider": "nvidia", "model": "nvidia/nemotron"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ]

    async def test_update_settings_rejects_retired_collection_fields(self, auth_client: AsyncClient):
        comma_events = await auth_client.put(
            "/api/settings",
            json={"webhook_events": "analysis_complete,order_filled"},
        )
        old_fallback_pair = await auth_client.put(
            "/api/settings",
            json={"fallback_llm_provider": "openai", "fallback_llm_model": "gpt-4o-mini"},
        )

        assert comma_events.status_code == 422
        assert old_fallback_pair.status_code == 422

    async def test_get_settings_unauthorized(self, async_client: AsyncClient):
        resp = await async_client.get("/api/settings")
        assert resp.status_code == 401

    async def test_get_meta(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert "investor_personas" in data
        assert "tools" in data
        assert "trading_modes" in data
        assert "brokers" in data

    async def test_get_llm_catalog(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/settings/llm-catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert data
        assert all(
            isinstance(entry.get("label"), str) and isinstance(entry.get("models"), list) for entry in data.values()
        )
