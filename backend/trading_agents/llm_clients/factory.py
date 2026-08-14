from __future__ import annotations

import os

from .base_client import BaseLLMClient
from .registry import llm_registry


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _litellm_proxy_url() -> str:
    base = os.getenv("LITELLM_PROXY_URL", "").strip().rstrip("/")
    if base and not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def create_llm_client(
    provider: str,
    model: str,
    **kwargs,
) -> BaseLLMClient:
    provider_lower = provider.lower()

    proxy_url = _litellm_proxy_url()
    if proxy_url and _truthy("LITELLM_ROUTE_ALL") and provider_lower != "ollama":
        from .litellm_proxy_client import LiteLLMProxyClient

        return LiteLLMProxyClient(
            model,
            upstream_provider=provider_lower,
            base_url=proxy_url,
            proxy_api_key=os.getenv("LITELLM_PROXY_KEY") or None,
            prefix_provider=_truthy("LITELLM_PREFIX_PROVIDER"),
            **kwargs,
        )

    if llm_registry.is_openai_compatible(provider_lower):
        from .openai_client import OpenAIClient

        return OpenAIClient(model, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(model, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient

        return GoogleClient(model, **kwargs)

    if provider_lower == "mistral":
        from .mistral_client import MistralClient

        return MistralClient(model, **kwargs)

    if provider_lower == "groq":
        from .groq_client import GroqClient

        return GroqClient(model, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
