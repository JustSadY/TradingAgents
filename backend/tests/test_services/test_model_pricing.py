import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from backend.core.model_pricing import (
    DEFAULT_CLOUD_PRICING,
    PRICE_OVERRIDES,
    _catalog,
    _longest_match,
    estimate_token_cost,
    estimate_total_token_cost,
    litellm_price_file,
    resolve_model_pricing,
)
from backend.services import token_analytics_service
from backend.services.analysis_stats_service import _calc_base
from backend.services.analysis_stats_service import estimate_cost as estimate_pre_run_cost


def test_price_table_is_readable():
    """A moved or renamed LiteLLM price file must fail here, loudly.

    Everything downstream degrades quietly: an unreadable table leaves every
    model on the conservative fallback, which still returns a plausible number
    on every dashboard. This is the only place that notices.
    """
    assert litellm_price_file().is_file(), (
        f"{litellm_price_file()} is missing. LiteLLM likely renamed it; update "
        "LITELLM_PRICE_FILE rather than leaving every model on the fallback rate."
    )

    catalog = _catalog()
    assert catalog, "the price table parsed to nothing"
    for provider in ("openai", "anthropic", "google"):
        assert catalog[provider], f"no {provider} rates found — check PROVIDER_CATALOG_KEYS"


def test_pricing_does_not_import_litellm():
    """Reading the file must not pull in the package.

    ``import litellm`` costs about three seconds and, by default, fetches a
    newer price map over the network — on a path that serves cost estimates to
    a page, inside an async endpoint. The file itself parses in about twelve
    milliseconds and behaves identically offline.

    This runs in a fresh interpreter on purpose: other tests in the suite do
    import litellm, so asserting against this process's ``sys.modules`` would
    pass or fail on test ordering rather than on the property.
    """
    probe = """
import sys
from backend.core.model_pricing import resolve_model_pricing
resolution = resolve_model_pricing("anthropic", "claude-opus-5")
assert resolution.source == "catalog", resolution
print("litellm" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[3],
        check=True,
    )

    assert result.stdout.strip() == "False", "resolving a price imported litellm"


def test_every_override_is_still_necessary():
    """An override that LiteLLM has caught up with is one to delete.

    The point of sourcing rates upstream is that the local list shrinks. Without
    this, an override silently shadows a corrected upstream price forever — the
    same failure the hand-written catalogue had, just smaller.
    """
    catalog = _catalog()
    redundant = []
    for provider, models in PRICE_OVERRIDES.items():
        for model, override in models.items():
            catalogued = _longest_match(catalog.get(provider, {}), model)
            if catalogued == override:
                redundant.append(f"{provider}/{model}")

    assert redundant == [], (
        f"LiteLLM now prices these identically: {redundant}. Delete them from "
        "PRICE_OVERRIDES so the upstream table stays the source."
    )


def test_catalogued_rate_replaces_a_stale_hand_written_one():
    """``gemini-3.6-flash`` was the drift this change was worth doing for.

    The hand-written catalogue carried it at the promotional flash rate it
    shared with 3.7, which had ended — so every estimate for that model was
    half of what the run cost. Nothing in the app could have noticed.
    """
    resolution = resolve_model_pricing("google", "gemini-3.6-flash")

    assert resolution.source == "catalog"
    assert resolution.pricing.input_per_million_usd == 1.5
    assert resolution.pricing.output_per_million_usd == 7.5


def test_dated_model_id_uses_its_own_rate_not_a_shorter_prefix():
    """A pinned snapshot ID must resolve to its own rate.

    ``claude-haiku-4-5-20251001`` has no catalogue entry, so it falls to the
    longest-prefix match. That must be ``claude-haiku-4-5`` rather than any
    shorter Claude key that also appears as a substring.
    """
    resolution = resolve_model_pricing("anthropic", "claude-haiku-4-5-20251001")

    assert resolution.source == "catalog"
    assert resolution.pricing.input_per_million_usd == 1.0
    assert resolution.pricing.output_per_million_usd == 5.0
    assert estimate_token_cost("anthropic", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 6.0


def test_a_model_name_is_not_priced_from_another_vendors_route():
    """LiteLLM knows ``llama-3.3-70b`` under Cerebras and Vercel, not NIM.

    Matching on the entry's own ``litellm_provider`` rather than on the key
    string is what keeps a cheaper vendor's rate for the same model name out of
    an NVIDIA estimate.
    """
    resolution = resolve_model_pricing("nvidia", "llama-3.3-70b")

    assert resolution.source == "exact"
    assert resolution.pricing.input_per_million_usd == 0.35


def test_pre_run_and_analytics_paths_share_the_same_catalogue():
    estimate = estimate_pre_run_cost("market,news", 1, "gpt-5.6-luna", "openai")

    assert estimate["estimated_cost_usd"] == round(
        estimate_total_token_cost("openai", "gpt-5.6-luna", estimate["estimated_tokens"]), 4
    )
    assert estimate["pricing_source"] == "catalog"
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
