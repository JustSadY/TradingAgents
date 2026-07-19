from __future__ import annotations

from .base_client import BaseLLMClient
from .registry import llm_registry


def create_llm_client(
    provider: str,
    model: str,
    **kwargs,
) -> BaseLLMClient:
    provider_lower = provider.lower()

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
