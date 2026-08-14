from __future__ import annotations

from .base_client import BaseLLMClient


def create_llm_client(
    provider: str,
    model: str,
    **kwargs,
) -> BaseLLMClient:
    """Create the sole provider implementation: LiteLLM."""
    try:
        from .litellm_client import LiteLLMClient
    except ImportError as exc:
        raise RuntimeError(
            "langchain-litellm is required for LLM access. Sync backend dependencies before running analyses."
        ) from exc
    return LiteLLMClient(model, provider=provider, **kwargs)
