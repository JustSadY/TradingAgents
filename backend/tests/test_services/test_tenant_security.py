from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.assistant import AssistantMessage
from backend.models.page_permission import UserPagePermission, UserSettingPermission
from backend.models.preset import ConfigPreset
from backend.models.user import User
from backend.repositories.assistant import add_message, get_messages
from backend.schemas.settings import SettingsUpdate
from backend.schemas.user import ApiKeySet
from backend.services.analysis_service import list_analysis_checkpoints
from backend.services.portfolio_assistant_service import clear_assistant_history, get_assistant_history
from backend.services.preset_service import PresetError, create_user_preset
from backend.services.settings_service import apply_preset_to_settings, apply_settings_update, get_or_create_settings
from backend.trading_agents.graph.checkpointer import checkpoint_scope, thread_id


class TestCheckpointTenantIsolation:
    def test_checkpoint_threads_include_analysis_scope(self):
        first = checkpoint_scope(user_id=101, analysis_id=501)
        second = checkpoint_scope(user_id=202, analysis_id=502)

        assert first != second
        assert thread_id("AAPL", "2026-07-26", first) != thread_id("AAPL", "2026-07-26", second)

    async def test_checkpoint_listing_uses_owned_analysis_scope(self, db: AsyncSession, test_user: User, monkeypatch):
        row = AnalysisResult(
            user_id=test_user.id,
            task_id="checkpoint-list-scope",
            ticker="AAPL",
            trade_date="2026-07-26",
            status="completed",
        )
        db.add(row)
        await db.flush()

        captured: dict[str, str] = {}

        async def fake_list(data_dir, ticker, date, scope):
            captured.update({"ticker": ticker, "date": date, "scope": scope})
            return []

        monkeypatch.setattr(
            "backend.trading_agents.graph.checkpointer.list_checkpoints_for_thread",
            fake_list,
        )

        assert await list_analysis_checkpoints(row.id, db, test_user) == []
        assert captured == {
            "ticker": "AAPL",
            "date": "2026-07-26",
            "scope": checkpoint_scope(test_user.id, row.id),
        }

    async def test_checkpoint_api_passes_service_arguments_in_declared_order(self, auth_client, monkeypatch):
        captured: dict = {}

        async def fake_list(analysis_id, db, current_user):
            captured.update({"analysis_id": analysis_id, "db": db, "user": current_user})
            return []

        monkeypatch.setattr("backend.services.analysis_service.list_analysis_checkpoints", fake_list)

        response = await auth_client.get("/api/analysis/123/checkpoints")

        assert response.status_code == 200
        assert captured["analysis_id"] == 123
        assert captured["user"].id is not None

class TestPresetHardening:
    async def test_legacy_preset_cannot_mass_assign_settings_owner(self, db: AsyncSession, test_user: User):
        settings = await get_or_create_settings(db, test_user)
        preset = ConfigPreset(
            user_id=test_user.id,
            name="malicious",
            settings_json='{"user_id": 999999, "llm_provider": "anthropic"}',
        )

        with pytest.raises(ValueError, match="unsupported settings: user_id"):
            await apply_preset_to_settings(db, test_user, preset)

        assert settings.user_id == test_user.id
        assert settings.llm_provider == "openai"

    async def test_preset_respects_settings_section_permissions(self, db: AsyncSession, test_user: User):
        db.add(UserSettingPermission(user_id=test_user.id, setting_key="presets", allowed=True))
        await db.flush()

        with pytest.raises(PresetError, match="section: llm"):
            await create_user_preset(
                db,
                None,
                test_user,
                name="LLM override",
                description="",
                settings_json='{"llm_provider": "anthropic"}',
            )

class TestAssistantTenantIsolation:
    async def test_admin_history_and_clear_are_still_self_scoped(
        self, db: AsyncSession, test_user: User, admin_user: User
    ):
        await add_message(db, test_user.id, "user", "tenant secret")
        await add_message(db, admin_user.id, "user", "admin note")

        history = await get_assistant_history(db, admin_user)
        assert [item["content"] for item in history] == ["admin note"]

        await clear_assistant_history(db, admin_user)
        assert await get_messages(db, admin_user.id) == []
        assert [m.content for m in await get_messages(db, test_user.id)] == ["tenant secret"]

    async def test_history_api_passes_user_not_integer(self, auth_client, db: AsyncSession, test_user: User):
        db.add(AssistantMessage(user_id=test_user.id, role="user", content="hello"))
        await db.flush()

        response = await auth_client.get("/api/assistant/history")

        assert response.status_code == 200
        assert [item["content"] for item in response.json()] == ["hello"]

class TestOllamaEndpointHardening:
    @pytest.mark.parametrize("api_key", ["http://169.254.169.254/latest/meta-data", "not-a-url-secret"])
    def test_user_cannot_store_any_ollama_tenant_credential(self, api_key):
        with pytest.raises(ValidationError, match="server administrator"):
            ApiKeySet(provider="ollama", api_key=api_key)

    def test_ollama_runtime_discards_tenant_url_and_uses_server_endpoint(self, monkeypatch):
        from backend.core import config as config_module
        from backend.trading_agents.llm_clients import litellm_client

        captured: dict = {}

        class FakeChatLiteLLM:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(litellm_client, "GuardedChatLiteLLM", FakeChatLiteLLM)
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(OLLAMA_BASE_URL="http://localhost:11434"),
        )

        client = litellm_client.LiteLLMClient(
            model="llama3.2",
            provider="ollama",
            api_key="http://169.254.169.254/latest/meta-data",
        )
        client.get_llm()

        assert captured["model"] == "ollama/llama3.2"
        assert captured["api_base"] == "http://localhost:11434"
        assert "api_key" not in captured
        assert client.base_url == "http://localhost:11434"
        assert "api_key" not in client.kwargs

class TestPagePermissionEnforcement:
    async def test_page_backed_analysis_route_denies_user_without_entitlement(self, async_client, auth_headers):
        response = await async_client.get("/api/analysis/latest", headers=auth_headers)

        assert response.status_code == 403

    async def test_shared_analysis_history_allows_chart_entitlement(
        self, async_client, auth_headers, db: AsyncSession, test_user: User
    ):
        db.add(UserPagePermission(user_id=test_user.id, page_key="chart", allowed=True))
        await db.flush()

        response = await async_client.get("/api/analysis/history", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    async def test_revoked_access_token_is_rejected_before_page_check(
        self, async_client, auth_headers, db: AsyncSession, test_user: User
    ):
        test_user.token_version = 1
        await db.flush()

        response = await async_client.get("/api/analysis/latest", headers=auth_headers)

        assert response.status_code == 401

class TestProfileMutationPermission:
    async def test_profile_reads_remain_available_for_auth_bootstrap(self, async_client, auth_headers):
        response = await async_client.get("/api/users/me", headers=auth_headers)

        assert response.status_code == 200

    async def test_profile_and_api_key_mutations_require_profile_page(self, async_client, auth_headers):
        mutations = [
            ("put", "/api/users/me", {"display_name": "Hidden profile"}),
            ("put", "/api/users/me/api-keys", {"provider": "openai", "api_key": "sk-test-123"}),
            ("delete", "/api/users/me/api-keys/openai", None),
        ]

        for method, path, payload in mutations:
            kwargs: dict = {"headers": auth_headers}
            if payload is not None:
                kwargs["json"] = payload
            response = await getattr(async_client, method)(path, **kwargs)
            assert response.status_code == 403, path

class TestWebhookSsrFHardening:
    async def test_settings_service_rejects_private_webhook_url(self, db: AsyncSession, test_user: User):
        settings = await get_or_create_settings(db, test_user)

        with pytest.raises(ValueError, match="disallowed internal address"):
            await apply_settings_update(db, settings, SettingsUpdate(webhook_url="http://127.0.0.1/hooks"))

    async def test_send_webhook_revalidates_legacy_private_url(self, monkeypatch):
        import httpx

        from backend.services.notification_service import send_webhook

        called = False

        class UnexpectedClient:
            def __init__(self, *args, **kwargs):
                nonlocal called
                called = True

        monkeypatch.setattr(httpx, "AsyncClient", UnexpectedClient)

        assert await send_webhook("http://127.0.0.1/hooks", "analysis_complete", {}) is False
        assert called is False

class TestSettingsSectionMutationEnforcement:
    async def test_hidden_setting_sections_cannot_be_mutated_directly(self, async_client, auth_headers):
        mutations = [
            ("put", "/api/settings/agents", {"agents": {}}),
            ("put", "/api/settings/tools", {"tools": {}}),
            ("post", "/api/settings/test-webhook", {"url": "http://127.0.0.1/hooks"}),
            ("post", "/api/personas", {"key": "private", "label": "Private"}),
            ("post", "/api/presets", {"name": "Private", "settings_json": "{}"}),
        ]

        for method, path, body in mutations:
            response = await getattr(async_client, method)(path, json=body, headers=auth_headers)
            assert response.status_code == 403, path

class TestAssistantPagePermissionEnforcement:
    async def test_assistant_exposes_only_tools_for_allowed_pages(self):
        from backend.services import portfolio_assistant_service as assistant

        user = SimpleNamespace(is_admin=False)
        tools = assistant._make_tools(None, user, {"analysis"})

        assert {tool.name for tool in tools} == {
            "get_analysis_history",
            "get_analysis_report",
            "run_stock_analysis",
        }

    async def test_assistant_read_helpers_fail_closed_without_page_access(self):
        from backend.services import portfolio_assistant_service as assistant

        user = SimpleNamespace(is_admin=False)
        allowed_pages: set[str] = set()
        checks = [
            (assistant._tool_get_portfolio_summary(None, user, allowed_pages), "Portfolio"),
            (assistant._tool_get_analysis_history(None, user, allowed_pages, "", 5), "Analysis"),
            (assistant._tool_get_analysis_report(None, user, allowed_pages, 1), "Analysis"),
            (assistant._tool_get_live_price(user, allowed_pages, "AAPL"), "Chart"),
            (assistant._tool_get_watchlist(None, user, allowed_pages), "Watchlist"),
            (assistant._tool_get_alerts(None, user, allowed_pages), "Alerts"),
        ]

        for call, label in checks:
            assert await call == f"Permission denied: you do not have access to the {label} page."

class TestTenantPerformanceContext:
    async def test_performance_context_forwards_user_scope(self, monkeypatch):
        from backend.services import performance_service

        captured: dict[str, int | None] = {}

        async def fake_attribution(db, user_id: int | None = None):
            captured["user_id"] = user_id
            return {"attribution": []}

        monkeypatch.setattr(performance_service, "get_analyst_attribution_stats", fake_attribution)

        assert await performance_service.get_analyst_performance_context(object(), user_id=42) == ""
        assert captured == {"user_id": 42}

    async def test_system_attribution_excludes_tenant_history(self, db: AsyncSession, test_user: User, monkeypatch):
        from backend.services import performance_service
        from backend.trading_agents.agents import analyst_registry

        monkeypatch.setattr(analyst_registry, "get_report_fields", lambda: {"market_report": "Market Analyst"})
        db.add_all(
            [
                AnalysisResult(
                    user_id=None,
                    ticker="AAPL",
                    trade_date="2026-07-29",
                    market_report="Rating: Buy",
                    raw_return=0.05,
                    status="completed",
                ),
                AnalysisResult(
                    user_id=test_user.id,
                    ticker="AAPL",
                    trade_date="2026-07-29",
                    market_report="Rating: Buy",
                    raw_return=0.05,
                    status="completed",
                ),
            ]
        )
        await db.flush()

        result = await performance_service.get_analyst_attribution_stats(db, user_id=None)

        assert result["total_evaluated_runs"] == 1
        assert result["attribution"] == [
            {
                "key": "market",
                "label": "Market Analyst",
                "total_predictions": 1,
                "correct_predictions": 1,
                "win_rate": 100.0,
                "weight": 100.0,
                "chronic_underperformer": False,
            }
        ]

class TestProxyAwareRateLimiting:
    @staticmethod
    def _request(client_ip: str, forwarded: str | None = None):
        from starlette.requests import Request

        headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": headers,
                "client": (client_ip, 12345),
                "server": ("testserver", 80),
            }
        )

    def test_forwarded_header_is_ignored_without_explicit_proxy_trust(self, monkeypatch):
        from backend.core import limiter as limiter_module

        monkeypatch.setattr(
            limiter_module,
            "get_settings",
            lambda: SimpleNamespace(TRUST_PROXY_HEADERS=False, TRUSTED_PROXY_CIDRS="10.0.0.0/8"),
        )

        assert limiter_module._client_ip(self._request("10.0.0.2", "203.0.113.9")) == "10.0.0.2"

    def test_valid_forwarded_header_is_used_only_from_a_trusted_proxy(self, monkeypatch):
        from backend.core import limiter as limiter_module

        monkeypatch.setattr(
            limiter_module,
            "get_settings",
            lambda: SimpleNamespace(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_CIDRS="10.0.0.0/8"),
        )

        assert limiter_module._client_ip(self._request("10.0.0.2", "198.51.100.9, 10.0.0.3")) == "198.51.100.9"
        assert limiter_module._client_ip(self._request("10.0.0.2", "not-an-ip")) == "10.0.0.2"

    def test_forwarded_header_cannot_be_forged_through_an_untrusted_peer(self, monkeypatch):
        from backend.core import limiter as limiter_module

        monkeypatch.setattr(
            limiter_module,
            "get_settings",
            lambda: SimpleNamespace(TRUST_PROXY_HEADERS=True, TRUSTED_PROXY_CIDRS="10.0.0.0/8"),
        )

        assert limiter_module._client_ip(self._request("198.51.100.20", "1.1.1.1")) == "198.51.100.20"
