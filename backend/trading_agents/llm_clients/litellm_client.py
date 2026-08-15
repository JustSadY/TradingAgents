from __future__ import annotations

from typing import Any

from langchain_litellm import ChatLiteLLM

from .base_client import (
    SDK_RETRIES,
    BaseLLMClient,
    global_llm_concurrency_guard,
    normalize_content,
)
from .registry import provider_requires_api_key

_PROVIDER_PREFIX = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "mistral": "mistral",
    "groq": "groq",
    "nvidia": "nvidia_nim",
    "deepseek": "deepseek",
    "ollama": "ollama",
}

_PROVIDER_BASE_URL = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


def routed_model(provider: str, model: str) -> str:
    """Return LiteLLM's canonical provider/model route."""
    provider = provider.strip().lower()
    prefix = _PROVIDER_PREFIX.get(provider)
    if prefix is None:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return model if model.startswith(f"{prefix}/") else f"{prefix}/{model}"


class GuardedChatLiteLLM(ChatLiteLLM):
    """ChatLiteLLM with the app's global concurrency and content normalization."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config=config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        async with global_llm_concurrency_guard():
            result = await super().ainvoke(input, config=config, **kwargs)
            return normalize_content(result)

    async def astream(self, *args, **kwargs):
        async with global_llm_concurrency_guard():
            async for chunk in super().astream(*args, **kwargs):
                yield chunk


class LiteLLMClient(BaseLLMClient):
    """Single provider implementation for all hosted/local chat models."""

    def __init__(
        self,
        model: str,
        *,
        provider: str,
        base_url: str | None = None,
        **kwargs,
    ):
        self.upstream_provider = provider.strip().lower()
        self.provider = "litellm"
        if self.upstream_provider not in _PROVIDER_PREFIX:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        if self.upstream_provider == "ollama":
            from backend.core.config import get_settings

            base_url = get_settings().OLLAMA_BASE_URL.rstrip("/")
            # Ollama is server-managed. A tenant value can never become its
            # credential or endpoint.
            kwargs.pop("api_key", None)
        elif base_url is None:
            base_url = _PROVIDER_BASE_URL.get(self.upstream_provider)

        super().__init__(routed_model(self.upstream_provider, model), base_url, **kwargs)

    def get_llm(self) -> Any:
        api_key = self.kwargs.get("api_key")
        if provider_requires_api_key(self.upstream_provider) and not api_key:
            raise ValueError(
                f"API key for provider '{self.upstream_provider}' is not set. "
                "Please provide it in your Profile or Settings."
            )

        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "streaming": True,
            "max_retries": int(self.kwargs.get("max_retries", SDK_RETRIES)),
        }
        if self.base_url:
            llm_kwargs["api_base"] = self.base_url
        if api_key:
            llm_kwargs["api_key"] = api_key

        for key in (
            "temperature",
            "max_tokens",
            "top_p",
            "top_k",
            "stop",
            "extra_headers",
            "organization",
        ):
            value = self.kwargs.get(key)
            if value is not None:
                llm_kwargs[key] = value

        callbacks_value = self.kwargs.get("callbacks")
        if callbacks_value is None:
            callbacks: list[Any] = []
        elif isinstance(callbacks_value, (list, tuple)):
            callbacks = list(callbacks_value)
        else:
            callbacks = [callbacks_value]

        from backend.core.observability import get_langfuse_callback

        langfuse_callback = get_langfuse_callback()
        if langfuse_callback is not None and langfuse_callback not in callbacks:
            callbacks.append(langfuse_callback)
        if callbacks:
            llm_kwargs["callbacks"] = callbacks

        timeout = self.kwargs.get("timeout")
        if timeout is not None:
            llm_kwargs["request_timeout"] = timeout

        model_kwargs: dict[str, Any] = {}
        for key in ("reasoning_effort", "effort", "prompt_caching"):
            value = self.kwargs.get(key)
            if value is not None:
                model_kwargs[key] = value

        # Existing UI stores Gemini thinking separately. LiteLLM translates
        # reasoning_effort into Gemini's thinking_level for Gemini 3+.
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level is not None and "reasoning_effort" not in model_kwargs:
            model_kwargs["reasoning_effort"] = thinking_level

        if model_kwargs:
            llm_kwargs["model_kwargs"] = model_kwargs

        return GuardedChatLiteLLM(**llm_kwargs)

    def validate_model(self) -> bool:
        # LiteLLM owns provider/model routing. The app registry is presentation
        # metadata rather than a second SDK validation layer.
        return True
