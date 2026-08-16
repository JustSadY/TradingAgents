"""Canonical, best-effort LLM pricing used by cost estimates and analytics.

Rates come from LiteLLM's price table, which ships inside the pinned
``litellm`` package and is maintained upstream against the providers' published
pricing. Before this, the catalogue below was written out by hand: nothing ever
told anyone it had gone stale, and the only symptom of a wrong rate is a wrong
number on a dashboard. LiteLLM's table agreed with thirteen of the nineteen
hand-written rows exactly and corrected a fourteenth — ``gemini-3.6-flash`` was
still carrying a promotional rate, so every estimate for that model was half of
what the run actually cost.

The application still does not claim to be a billing system. Providers change
prices and users can configure model IDs newer than the pinned table, so
callers get a :class:`PricingResolution` rather than a bare number: catalogue
matches are distinguished from the conservative fallback, and local models
explicitly cost zero.

Two deliberate choices:

* The table is read straight from the file the ``litellm`` package ships, not
  through ``import litellm``. Importing the package takes about three seconds
  and, by default, fetches a newer map over the network at import time — a
  hidden request on a path that serves cost estimates, and one that silently
  falls back to the shipped file when a deployment cannot reach GitHub. Reading
  the file takes about twelve milliseconds and behaves the same everywhere.
  Freshness comes from bumping the pinned ``litellm`` version, which
  ``uv.lock`` already records.
* :data:`PRICE_OVERRIDES` holds only what LiteLLM's shipped table does not have
  or routes to a different vendor. ``test_model_pricing.py`` fails when an
  override stops being necessary, so the list shrinks as LiteLLM catches up
  instead of quietly rotting the way the full table did.

Rates are USD per one million tokens.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Literal

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Input and output rates in USD per one million tokens."""

    input_per_million_usd: float
    output_per_million_usd: float


PricingSource = Literal[
    "catalog",
    "exact",
    "model_id",
    "provider_fallback",
    "unknown_provider",
    "local",
]


@dataclass(frozen=True)
class PricingResolution:
    """The rate selected for a model and whether it is a fallback estimate."""

    pricing: ModelPricing
    source: PricingSource

    @property
    def is_fallback(self) -> bool:
        return self.source in {"provider_fallback", "unknown_provider"}


#: The file LiteLLM ships its price table in. Named here rather than reached
#: through ``import litellm`` for the reasons in the module docstring; a release
#: that renames it fails ``test_price_table_is_readable``, instead of silently
#: costing every model at :data:`DEFAULT_CLOUD_PRICING`.
LITELLM_PRICE_FILE = "model_prices_and_context_window_backup.json"

#: This repository's provider keys mapped to the ``litellm_provider`` values
#: that may price them. Matching on the entry's own provider field rather than
#: on a key prefix is what stops another vendor's route for the same model name
#: being accepted: LiteLLM knows ``llama-3.3-70b`` under Cerebras and Vercel,
#: neither of which is what ``nvidia`` bills.
PROVIDER_CATALOG_KEYS: dict[str, frozenset[str]] = {
    "openai": frozenset({"openai"}),
    "anthropic": frozenset({"anthropic"}),
    "google": frozenset({"gemini", "vertex_ai-language-models"}),
    "mistral": frozenset({"mistral"}),
    "groq": frozenset({"groq"}),
    "deepseek": frozenset({"deepseek"}),
    "nvidia": frozenset({"nvidia_nim"}),
}

#: Rates LiteLLM's shipped table cannot supply. Each entry needs a reason, and
#: each is asserted to still be necessary by the test suite.
PRICE_OVERRIDES: dict[str, dict[str, ModelPricing]] = {
    "google": {
        # Newer than the pinned table.
        "gemini-3.7-flash": ModelPricing(0.75, 3.75),
        # LiteLLM carries only the dated `-preview` keys for this one, which do
        # not match the plain ID the registry offers.
        "gemini-3.1-pro": ModelPricing(2.0, 12.0),
    },
    "nvidia": {
        # LiteLLM's three `nvidia_nim` entries are rerank models. NIM's llama
        # inference rates are not in the table under any provider we bill.
        "llama-3.1-70b": ModelPricing(0.35, 0.35),
        "llama-3.1-405b": ModelPricing(2.0, 2.0),
        "llama-3.3-70b": ModelPricing(0.35, 0.35),
    },
}

KNOWN_CLOUD_PROVIDERS = frozenset(PROVIDER_CATALOG_KEYS)
LOCAL_PROVIDERS = frozenset({"ollama"})
DEFAULT_CLOUD_PRICING = ModelPricing(2.0, 8.0)
ZERO_PRICING = ModelPricing(0.0, 0.0)

_PER_MILLION = 1_000_000


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold()


def litellm_price_file() -> Path:
    """Locate the price table without executing ``litellm/__init__.py``.

    ``find_spec`` only asks the path finders where the package lives; it does
    not run it. ``importlib.resources.files`` would, and that import is the
    three-second network-fetching one this module exists to avoid.
    """
    spec = find_spec("litellm")
    if spec is None or not spec.submodule_search_locations:
        raise ModuleNotFoundError("litellm is not installed")
    return Path(next(iter(spec.submodule_search_locations))) / LITELLM_PRICE_FILE


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, ModelPricing]]:
    """LiteLLM's table, indexed the way this module asks questions of it.

    An unreadable or unrecognisable file degrades to the empty catalogue, which
    leaves every model on the conservative fallback rather than failing a
    request. The accompanying test is what makes that loud.
    """
    try:
        raw = json.loads(litellm_price_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - any failure here means "no catalogue"
        _logger.exception("Could not read the LiteLLM price table; falling back to estimates")
        return {}

    by_provider: dict[str, dict[str, ModelPricing]] = {provider: {} for provider in PROVIDER_CATALOG_KEYS}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        litellm_provider = entry.get("litellm_provider")
        input_cost = entry.get("input_cost_per_token")
        output_cost = entry.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            continue
        for provider, accepted in PROVIDER_CATALOG_KEYS.items():
            if litellm_provider not in accepted:
                continue
            # Entries are keyed either bare or vendor-prefixed ("gemini/x").
            model = key.rsplit("/", 1)[-1].casefold()
            by_provider[provider].setdefault(
                model,
                ModelPricing(float(input_cost) * _PER_MILLION, float(output_cost) * _PER_MILLION),
            )
    return by_provider


def _longest_match(rates: dict[str, ModelPricing], model: str) -> ModelPricing | None:
    """Exact match, else the longest catalogue key contained in the model ID.

    Pinned snapshot IDs are why this is not an equality check:
    ``claude-haiku-4-5-20251001`` has no entry of its own and must resolve to
    ``claude-haiku-4-5``, not to any shorter Claude key that is also a
    substring of it.
    """
    if model in rates:
        return rates[model]
    for key in sorted(rates, key=len, reverse=True):
        if key in model:
            return rates[key]
    return None


def _override(provider: str, model: str) -> ModelPricing | None:
    return _longest_match(PRICE_OVERRIDES.get(provider, {}), model)


@lru_cache(maxsize=512)
def _resolve_normalized(provider: str, model: str) -> PricingResolution:
    if provider in LOCAL_PROVIDERS:
        return PricingResolution(ZERO_PRICING, "local")

    if provider:
        override = _override(provider, model)
        if override is not None:
            return PricingResolution(override, "exact")

        catalogued = _longest_match(_catalog().get(provider, {}), model)
        if catalogued is not None:
            return PricingResolution(catalogued, "catalog")

        source: PricingSource = "provider_fallback" if provider in KNOWN_CLOUD_PROVIDERS else "unknown_provider"
        _logger.warning(
            "No LLM price for provider=%r model=%r; using conservative %s estimate",
            provider,
            model or "(unset)",
            source,
        )
        return PricingResolution(DEFAULT_CLOUD_PRICING, source)

    # No provider given: accept a model ID only if it means one thing across
    # every provider, so an ambiguous name is estimated rather than guessed.
    candidates = {
        price
        for candidate_provider in PROVIDER_CATALOG_KEYS
        if (price := _override(candidate_provider, model) or _longest_match(_catalog().get(candidate_provider, {}), model))
        is not None
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
        / _PER_MILLION,
        6,
    )


def estimate_total_token_cost(provider: str | None, model: str | None, total_tokens: int) -> float:
    """Estimate a pre-run cost when only a total token estimate is available.

    The input/output split is unknown before a run, so use the same catalogue's
    blended rate instead of a separate per-1K table.
    """
    price = resolve_model_pricing(provider, model).pricing
    blended_per_million = (price.input_per_million_usd + price.output_per_million_usd) / 2
    return round(max(0, total_tokens) * blended_per_million / _PER_MILLION, 6)
