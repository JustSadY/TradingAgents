"""Regression coverage for the canonical LLM failover runtime contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.settings import AppSettings
from backend.services.analysis.config_builder import build_analysis_config
from backend.trading_agents.config import FallbackLLMConfig, TradingAgentsConfig, normalize_fallback_llm_chain
from backend.trading_agents.graph.trading_graph import TradingAgentsGraph


def _graph_with_config(config: dict) -> TradingAgentsGraph:
    """Create the small graph shell needed by ``_with_fallback`` tests."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.callbacks = []
    return graph

def test_fallback_chain_is_normalized_in_default_runtime_config():
    config = TradingAgentsConfig(
        fallback_llm_chain=[
            {"provider": " NVIDIA ", "model": " nvidia/nemotron "},
            {"provider": "OpenAI", "model": "gpt-4o-mini"},
        ]
    )

    assert config.to_dict()["fallback_llm_chain"] == [
        {"provider": "nvidia", "model": "nvidia/nemotron"},
        {"provider": "openai", "model": "gpt-4o-mini"},
    ]

    assert normalize_fallback_llm_chain([FallbackLLMConfig(provider="NVIDIA", model="nemotron")]) == [
        {"provider": "nvidia", "model": "nemotron"}
    ]

@pytest.mark.parametrize(
    "value",
    [
        {"provider": "openai", "model": "gpt-4o-mini"},
        [{"provider": "", "model": "gpt-4o-mini"}],
        [{"provider": "openai", "model": ""}],
        [{"provider": "openai", "model": "gpt-4o-mini", "extra": "not allowed"}],
        [{"provider": "openai", "model": "a"}] * 4,
    ],
)
def test_fallback_chain_rejects_noncanonical_entries(value):
    with pytest.raises((ValidationError, ValueError)):
        TradingAgentsConfig(fallback_llm_chain=value)

    with pytest.raises(ValueError):
        normalize_fallback_llm_chain(value)

def test_graph_without_a_canonical_chain_leaves_primary_unwrapped():
    primary = object()
    graph = _graph_with_config({})

    assert graph._with_fallback(primary, "openai", "gpt-4o-mini") is primary

def test_graph_rejects_an_invalid_canonical_chain():
    graph = _graph_with_config({"fallback_llm_chain": {"provider": "nvidia", "model": "nemotron"}})

    with pytest.raises(ValueError, match="fallback_llm_chain"):
        graph._with_fallback(object(), "openai", "gpt-4o-mini")

def test_analysis_config_emits_only_the_canonical_fallback_chain():
    settings = AppSettings(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        fallback_llm_chain=[{"provider": " NVIDIA ", "model": " nvidia/nemotron "}],
    )

    config = build_analysis_config(settings)

    assert config["fallback_llm_chain"] == [{"provider": "nvidia", "model": "nvidia/nemotron"}]
    assert "fallback_llm_provider" not in config
    assert "fallback_llm_model" not in config

def test_graph_builds_fallbacks_only_from_ordered_chain(monkeypatch):
    from backend.trading_agents.graph import trading_graph
    from backend.trading_agents.llm_clients import fallback as fallback_module

    primary = object()
    created: list[tuple[str, str, dict]] = []

    class FakeClient:
        def __init__(self, provider: str, model: str, kwargs: dict):
            self.provider = provider
            self.model = model
            self.kwargs = kwargs

        def get_llm(self):
            return f"{self.provider}/{self.model}"

    class CapturedFallback:
        def __init__(self, received_primary, fallbacks):
            self.primary = received_primary
            self.fallbacks = fallbacks

    def create_client(*, provider: str, model: str, **kwargs):
        created.append((provider, model, kwargs))
        return FakeClient(provider, model, kwargs)

    monkeypatch.setattr(trading_graph, "create_llm_client", create_client)
    monkeypatch.setattr(fallback_module, "FallbackLLM", CapturedFallback)

    graph = _graph_with_config(
        {
            "fallback_llm_chain": [
                {"provider": "nvidia", "model": "nvidia/nemotron"},
                {"provider": "openai", "model": "gpt-4o-mini"},
            ],
            "user_api_keys": {"nvidia": "nv-key", "ollama": "http://stale.invalid"},
        }
    )

    result = graph._with_fallback(primary, "openai", "gpt-4o-mini")

    assert isinstance(result, CapturedFallback)
    assert result.primary is primary
    assert result.fallbacks == ["nvidia/nvidia/nemotron"]
    assert created == [("nvidia", "nvidia/nemotron", {"api_key": "nv-key"})]

def test_ollama_never_receives_a_tenant_api_value():
    graph = _graph_with_config(
        {
            "llm_provider": "ollama",
            "api_key": "http://stale.internal",
            "user_api_keys": {"ollama": "http://stale.internal"},
        }
    )

    assert graph._get_provider_kwargs("ollama") == {}
