from __future__ import annotations

import logging
from typing import Any

from langchain_groq import ChatGroq

from .base_client import BaseLLMClient, is_quota_exhausted, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)


class NormalizedChatGroq(ChatGroq):
    def invoke(self, input_value, config=None, **kwargs):
        try:
            return normalize_content(super().invoke(input_value, config, **kwargs))
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Groq quota exhausted: %s", exc)
            raise

    async def ainvoke(self, input_value, config=None, **kwargs):
        try:
            result = await super().ainvoke(input_value, config, **kwargs)
            return normalize_content(result)
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Groq quota exhausted: %s", exc)
            raise


_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "api_key",
    "callbacks",
    "temperature",
    "max_tokens",
    "top_p",
    "stop",
    "frequency_penalty",
    "presence_penalty",
)


class GroqClient(BaseLLMClient):
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
            raise ValueError(
                "API key for Groq is not set. "
                "Please provide it in your Profile or Settings."
            )
        llm_kwargs["api_key"] = api_key

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key == "api_key":
                continue
            if key not in self.kwargs:
                continue
            value = self.kwargs[key]
            if key in ("temperature", "frequency_penalty", "presence_penalty", "top_p"):
                llm_kwargs[key] = float(value)
            elif key in ("max_tokens", "max_retries"):
                llm_kwargs[key] = int(value)
            else:
                llm_kwargs[key] = value

        return NormalizedChatGroq(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("groq", self.model)
