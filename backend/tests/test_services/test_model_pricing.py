from types import SimpleNamespace

from backend.core.model_pricing import (
    DEFAULT_CLOUD_PRICING,
    estimate_token_cost,
    estimate_total_token_cost,
    resolve_model_pricing,
)
from backend.services import token_analytics_service
from backend.services.analysis_stats_service import _calc_base
from backend.services.analysis_stats_service import estimate_cost as estimate_pre_run_cost


def test_dated_model_id_uses_its_own_rate_not_a_shorter_prefix():
    """A pinned snapshot ID must resolve to its own rate.

    ``claude-haiku-4-5-20251001`` has no exact catalogue entry, so it falls to
    the longest-prefix match.  That must be ``claude-haiku-4-5`` rather than any
    shorter Claude key that also appears as a substring.
    """
    resolution = resolve_model_pricing("anthropic", "claude-haiku-4-5-20251001")

    assert resolution.source == "exact"
    assert resolution.pricing.input_per_million_usd == 1.0
    assert resolution.pricing.output_per_million_usd == 5.0
    assert estimate_token_cost("anthropic", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 6.0

def test_pre_run_and_analytics_paths_share_the_same_catalogue():
    estimate = estimate_pre_run_cost("market,news", 1, "gpt-5.6-luna", "openai")

    assert estimate["estimated_cost_usd"] == round(
        estimate_total_token_cost("openai", "gpt-5.6-luna", estimate["estimated_tokens"]), 4
    )
    assert estimate["pricing_source"] == "exact"
    assert estimate["pricing_is_fallback"] is False

    row = SimpleNamespace(
        duration_seconds=1.0,
        tokens_in=1_000_000,
        tokens_out=1_000_000,
        llm_provider="openai",
        llm_model="gpt-5.6-luna",
        raw_return=None,
        signal=None,
    )
    assert _calc_base([row])["avg_cost_usd"] == 1.4

def test_unknown_cloud_model_is_labelled_as_a_conservative_fallback():
    resolution = resolve_model_pricing("groq", "a-newly-released-model")

    assert resolution.source == "provider_fallback"
    assert resolution.is_fallback is True
    assert resolution.pricing == DEFAULT_CLOUD_PRICING

def test_local_ollama_model_has_no_provider_token_charge():
    resolution = resolve_model_pricing("ollama", "custom-local-model")

    assert resolution.source == "local"
    assert resolution.is_fallback is False
    assert estimate_token_cost("ollama", "custom-local-model", 1_000_000, 1_000_000) == 0.0

async def test_token_usage_breakdown_exposes_fallback_pricing(monkeypatch):
    row = SimpleNamespace(
        llm_provider="groq",
        llm_model="a-newly-released-model",
        tokens_in=100,
        tokens_out=50,
        analyses=1,
    )

    async def token_rows(*_args):
        return [row]

    async def daily_rows(*_args):
        return []

    monkeypatch.setattr(token_analytics_service.repo, "get_token_usage_rows", token_rows)
    monkeypatch.setattr(token_analytics_service.repo, "get_daily_token_usage_rows", daily_rows)

    result = await token_analytics_service.get_token_analytics(object(), 1)

    assert result["breakdown"][0]["pricing_source"] == "provider_fallback"
    assert result["breakdown"][0]["pricing_is_fallback"] is True
