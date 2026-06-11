from typing import Any

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        result = await super().ainvoke(input, config, **kwargs)
        return normalize_content(result)

    def _use_responses_api(self, payload: dict) -> bool:
        # Always use Chat Completions API — Responses API is not needed for
        # tool-calling agents and causes 404 on some account tiers.
        return False

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        method = method or caps.preferred_structured_method
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return super().with_structured_output(schema, method=method, **kwargs)


_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "reasoning_effort",
    "api_key",
    "callbacks",
    "http_client",
    "http_async_client",
)

_PROVIDER_BASE_URL = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        # stream_usage makes OpenAI include token usage in streamed responses;
        # without it every streaming call reports no usage and the per-analysis
        # token counters silently stay at zero.
        llm_kwargs = {"model": self.model, "streaming": True, "stream_usage": True}

        # Determine base URL
        resolved_base_url = self.base_url or _PROVIDER_BASE_URL.get(self.provider)
        if resolved_base_url:
            llm_kwargs["base_url"] = resolved_base_url

        # Determine API Key (NO .env lookups)
        api_key = self.kwargs.get("api_key")
        if api_key:
            llm_kwargs["api_key"] = api_key
        else:
            raise ValueError(
                f"API key for provider '{self.provider}' is not set. Please provide it in your Profile or Settings."
            )

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
