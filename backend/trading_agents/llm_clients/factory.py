from typing import Optional
from .base_client import BaseLLMClient
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek",
    "qwen", "qwen-cn",
    "glm", "glm-cn",
    "minimax", "minimax-cn",
    "ollama", "openrouter",
    "litellm", "nvidia",
)
def create_llm_client(
    provider: str,
    model: str,
    **kwargs,
) -> BaseLLMClient:
    provider_lower = provider.lower()
    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, provider=provider_lower, **kwargs)
    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, **kwargs)
    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, **kwargs)
    raise ValueError(f"Unsupported LLM provider: {provider}")
