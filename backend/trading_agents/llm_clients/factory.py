from __future__ import annotations
from typing import Optional
from .registry import llm_registry
from .base_client import BaseLLMClient

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

    raise ValueError(f"Unsupported LLM provider: {provider}")
