from __future__ import annotations

from types import SimpleNamespace

from backend.services.performance_service import _create_reflector_for_row


async def test_reflection_uses_analysis_owner_provider_model_and_api_key(monkeypatch) -> None:
    captured = {}
    owner = SimpleNamespace(id=42)

    async def fake_get_user_by_id(_db, user_id):
        assert user_id == 42
        return owner

    class FakeClient:
        def get_llm(self):
            return "configured-llm"

    def fake_create_llm_client(*, provider, model, **kwargs):
        captured.update(provider=provider, model=model, **kwargs)
        return FakeClient()

    class FakeReflector:
        def __init__(self, llm):
            self.llm = llm

    monkeypatch.setattr("backend.repositories.users.get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: "tenant-key")
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: True)
    monkeypatch.setattr("backend.trading_agents.llm_clients.create_llm_client", fake_create_llm_client)
    monkeypatch.setattr("backend.trading_agents.graph.reflection.Reflector", FakeReflector)

    reflector = await _create_reflector_for_row(
        object(),
        SimpleNamespace(user_id=42),
        SimpleNamespace(llm_provider="nvidia", llm_model="meta/llama-test"),
    )

    assert reflector.llm == "configured-llm"
    assert captured == {
        "provider": "nvidia",
        "model": "meta/llama-test",
        "api_key": "tenant-key",
    }


async def test_reflection_rejects_hosted_provider_without_owner_key(monkeypatch) -> None:
    async def fake_get_user_by_id(_db, _user_id):
        return SimpleNamespace(id=42)

    monkeypatch.setattr("backend.repositories.users.get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: True)

    try:
        await _create_reflector_for_row(
            object(),
            SimpleNamespace(user_id=42),
            SimpleNamespace(llm_provider="openai", llm_model="gpt-test"),
        )
    except ValueError as exc:
        assert "No stored API key" in str(exc)
    else:
        raise AssertionError("Hosted reflection without an API key must fail closed")
