from __future__ import annotations

import logging
from typing import Any

from langchain_mistralai import ChatMistralAI

from .base_client import BaseLLMClient, is_quota_exhausted, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)

_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "api_key",
    "callbacks",
    "http_client",
    "http_async_client",
    "temperature",
    "max_tokens",
    "top_p",
    "stop",
    "frequency_penalty",
    "presence_penalty",
)

class NormalizedChatMistralAI(ChatMistralAI):
    def invoke(self, input_value, config=None, **kwargs):
        try:
            return normalize_content(super().invoke(input_value, config, **kwargs))
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Mistral AI quota exhausted: %s", exc)
            raise

    async def ainvoke(self, input_value, config=None, **kwargs):
        try:
            result = await super().ainvoke(input_value, config, **kwargs)
            return normalize_content(result)
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Mistral AI quota exhausted: %s", exc)
            raise

class MistralClient(BaseLLMClient):
    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "streaming": True,
            "stream_usage": True,
        }

        api_key = self.kwargs.get("api_key")
        if not api_key:
            raise ValueError("API key for Mistral AI is not set. Please provide it in your Profile or Settings.")
        llm_kwargs["mistral_api_key"] = api_key

        if self.base_url:
            llm_kwargs["endpoint"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key == "api_key":
                continue
            if key not in self.kwargs:
                continue
            value = self.kwargs[key]
            if key == "max_tokens":
                llm_kwargs["max_tokens"] = int(value)
            elif key in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
                llm_kwargs[key] = float(value)
            elif key in ("timeout", "max_retries"):
                llm_kwargs[key] = value
            elif key in ("callbacks", "http_client", "http_async_client"):
                llm_kwargs[key] = value
            else:
                llm_kwargs[key] = value

        return NormalizedChatMistralAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("mistral", self.model)
