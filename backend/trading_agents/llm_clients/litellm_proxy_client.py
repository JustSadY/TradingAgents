from __future__ import annotations

from typing import Any

from .base_client import SDK_RETRIES, BaseLLMClient
from .openai_client import NormalizedChatOpenAI


class LiteLLMProxyClient(BaseLLMClient):
    """OpenAI-compatible client routed through a server-owned LiteLLM Proxy."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        proxy_api_key: str | None = None,
        upstream_provider: str = "",
        prefix_provider: bool = False,
        **kwargs,
    ):
        self.provider = "litellm"
        self.upstream_provider = upstream_provider.strip().lower()
        routed_model = model
        if prefix_provider and self.upstream_provider and "/" not in model:
            routed_model = f"{self.upstream_provider}/{model}"
        self.proxy_api_key = proxy_api_key or "sk-litellm-proxy"
        super().__init__(routed_model, base_url.rstrip("/"), **kwargs)

    def get_llm(self) -> Any:
        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.proxy_api_key,
            "streaming": True,
            "stream_usage": True,
            "max_retries": SDK_RETRIES,
        }
        for key in (
            "timeout",
            "reasoning_effort",
            "callbacks",
            "http_client",
            "http_async_client",
            "temperature",
            "max_tokens",
            "top_p",
            "stop",
            "frequency_penalty",
            "presence_penalty",
        ):
            if key in self.kwargs and self.kwargs[key] is not None:
                llm_kwargs[key] = self.kwargs[key]
        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        # Proxy-side aliases/routing are the source of truth.
        return True
