"""Canonical, best-effort LLM pricing used by cost estimates and analytics.

The application intentionally keeps a small, static price catalogue instead of
claiming to be a billing system.  Providers can change prices and users can
configure model IDs that are newer than this catalogue.  Callers therefore get
a :class:`PricingResolution`, not just a bare number: exact matches are
distinguished from the conservative fallback and local models explicitly cost
zero.

Rates are USD per one million tokens.  Keep provider/model aliases here so all
cost paths resolve the same model ID in the same way.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Input and output rates in USD per one million tokens."""

    input_per_million_usd: float
    output_per_million_usd: float


PricingSource = Literal["exact", "model_id", "provider_fallback", "unknown_provider", "local"]


@dataclass(frozen=True)
class PricingResolution:
    """The rate selected for a model and whether it is a fallback estimate."""

    pricing: ModelPricing
    source: PricingSource

    @property
    def is_fallback(self) -> bool:
        return self.source in {"provider_fallback", "unknown_provider"}


# This is the sole model-price catalogue.  Matching supports versioned model
# IDs (for example ``gpt-4o-mini-2024-07-18``) by selecting the longest known
# model key, avoiding the old ``gpt-4o``-before-``gpt-4o-mini`` prefix bug.
MODEL_PRICING: dict[str, dict[str, ModelPricing]] = {
    "openai": {
        "gpt-4o-mini": ModelPricing(0.15, 0.60),
        "gpt-4o": ModelPricing(5.0, 15.0),
        "gpt-4-turbo": ModelPricing(10.0, 30.0),
        "gpt-3.5-turbo": ModelPricing(0.50, 1.50),
        "o1-mini": ModelPricing(3.0, 12.0),
        "o1": ModelPricing(15.0, 60.0),
        "o3-mini": ModelPricing(1.10, 4.40),
        "o4-mini": ModelPricing(1.10, 4.40),
    },
    "anthropic": {
        "claude-3-5-sonnet": ModelPricing(3.0, 15.0),
        "claude-3-5-haiku": ModelPricing(0.80, 4.0),
        "claude-3-opus": ModelPricing(15.0, 75.0),
        "claude-sonnet-4": ModelPricing(3.0, 15.0),
        "claude-haiku-4": ModelPricing(0.80, 4.0),
        "claude-opus-4": ModelPricing(15.0, 75.0),
    },
    "google": {
        "gemini-1.5-pro": ModelPricing(3.50, 10.50),
        "gemini-1.5-flash": ModelPricing(0.075, 0.30),
        "gemini-2.0-flash": ModelPricing(0.075, 0.30),
        "gemini-2.5-pro": ModelPricing(7.0, 21.0),
        "gemini-2.5-flash": ModelPricing(0.15, 0.60),
    },
    "nvidia": {
        "llama-3.1-70b": ModelPricing(0.35, 0.35),
        "llama-3.1-405b": ModelPricing(2.0, 2.0),
        "llama-3.3-70b": ModelPricing(0.35, 0.35),
    },
}

# Catalogued providers without per-model prices still receive an explicit,
# labelled estimate rather than silently pretending an arbitrary model is an
# exact match.  Ollama executes locally and has no provider token charge.
KNOWN_CLOUD_PROVIDERS = frozenset({*MODEL_PRICING, "mistral", "groq", "deepseek"})
LOCAL_PROVIDERS = frozenset({"ollama"})
DEFAULT_CLOUD_PRICING = ModelPricing(2.0, 8.0)
ZERO_PRICING = ModelPricing(0.0, 0.0)


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold()


def _matching_price(provider: str, model: str) -> ModelPricing | None:
    """Return an exact/longest-prefix price for a provider/model pair."""
    rates = MODEL_PRICING.get(provider, {})
    if model in rates:
        return rates[model]

    for key in sorted(rates, key=len, reverse=True):
        if key in model:
            return rates[key]
    return None


@lru_cache(maxsize=512)
def _resolve_normalized(provider: str, model: str) -> PricingResolution:
    if provider in LOCAL_PROVIDERS:
        return PricingResolution(ZERO_PRICING, "local")

    if provider:
        match = _matching_price(provider, model)
        if match is not None:
            return PricingResolution(match, "exact")

        source: PricingSource = "provider_fallback" if provider in KNOWN_CLOUD_PROVIDERS else "unknown_provider"
        _logger.warning(
            "No exact LLM price for provider=%r model=%r; using conservative %s estimate",
            provider,
            model or "(unset)",
            source,
        )
        return PricingResolution(DEFAULT_CLOUD_PRICING, source)

    # Some historical records predate the provider column.  A unique model ID
    # is still safe to price exactly; callers can expose ``model_id`` so this
    # inference is not hidden from users.
    candidates = {
        price
        for candidate_provider in MODEL_PRICING
        if (price := _matching_price(candidate_provider, model)) is not None
    }
    if len(candidates) == 1:
        return PricingResolution(candidates.pop(), "model_id")

    _logger.warning(
        "No provider/exact LLM price for model=%r; using conservative unknown-provider estimate",
        model or "(unset)",
    )
    return PricingResolution(DEFAULT_CLOUD_PRICING, "unknown_provider")


def resolve_model_pricing(provider: str | None, model: str | None) -> PricingResolution:
    """Resolve a model rate and retain whether the result is a fallback."""
    return _resolve_normalized(_normalize(provider), _normalize(model))


def estimate_token_cost(
    provider: str | None,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
) -> float:
    """Estimate USD cost for measured input/output token counts."""
    price = resolve_model_pricing(provider, model).pricing
    return round(
        (max(0, tokens_in) * price.input_per_million_usd + max(0, tokens_out) * price.output_per_million_usd)
        / 1_000_000,
        6,
    )


def estimate_total_token_cost(provider: str | None, model: str | None, total_tokens: int) -> float:
    """Estimate a pre-run cost when only a total token estimate is available.

    The input/output split is unknown before a run, so use the same catalogue's
    blended rate instead of a separate per-1K table.
    """
    price = resolve_model_pricing(provider, model).pricing
    blended_per_million = (price.input_per_million_usd + price.output_per_million_usd) / 2
    return round(max(0, total_tokens) * blended_per_million / 1_000_000, 6)
