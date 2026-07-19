import logging
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, is_quota_exhausted, normalize_content
from .validators import validate_model

_logger = logging.getLogger(__name__)

# Only worth a cache breakpoint once the cached prefix is large enough to beat
# Anthropic's minimum cacheable size; below this the write overhead isn't repaid.
_MIN_CACHEABLE_CHARS = 2000


def _apply_cache_control(input_value: Any) -> Any:
    """Mark the system prompt with an ephemeral cache breakpoint.

    Within an analyst's tool loop (and structured retries) the same large system
    prompt is re-sent on every round-trip while only the trailing messages grow.
    Tagging the system message lets Anthropic serve that stable prefix from its
    prompt cache (~10% of the input price on a hit) instead of re-billing it.

    Returns a message list when it can safely rewrite the system message, else
    the input unchanged (so non-message inputs pass straight through)."""
    try:
        from langchain_core.messages import SystemMessage

        if hasattr(input_value, "to_messages"):
            messages = list(input_value.to_messages())
        elif isinstance(input_value, list):
            messages = list(input_value)
        else:
            return input_value

        for msg in messages:
            if isinstance(msg, SystemMessage) and isinstance(msg.content, str):
                if len(msg.content) >= _MIN_CACHEABLE_CHARS:
                    msg.content = [{"type": "text", "text": msg.content, "cache_control": {"type": "ephemeral"}}]
                break  # one breakpoint on the system prefix is enough
        return messages
    # caching is an optimisation, never break the call
    except Exception as exc:  # noqa: BLE001
        _logger.debug("prompt caching skipped: %s", exc)
        return input_value


_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "api_key",
    "max_tokens",
    "callbacks",
    "http_client",
    "http_async_client",
    "effort",
)
_EFFORT_EXACT = {
    "claude-mythos-preview",
}
_EFFORT_PATTERN = re.compile(r"^claude-(opus|sonnet)-\d+-\d+$")


def _supports_effort(model: str) -> bool:
    model_lc = model.lower()
    return model_lc in _EFFORT_EXACT or bool(_EFFORT_PATTERN.match(model_lc))


class NormalizedChatAnthropic(ChatAnthropic):
    # Set by the client factory; when True the system prompt is cache-tagged.
    prompt_caching: bool = False

    def invoke(self, input_value, config=None, **kwargs):
        try:
            if self.prompt_caching:
                input_value = _apply_cache_control(input_value)
            return normalize_content(super().invoke(input_value, config, **kwargs))
        except Exception as exc:
            if is_quota_exhausted(exc):
                _logger.warning("Anthropic quota exhausted: %s", exc)
            raise

    async def ainvoke(self, input_value, config=None, **kwargs):
        try:
            if self.prompt_caching:
                input_value = _apply_cache_control(input_value)
            result = await super().ainvoke(input_value, config, **kwargs)
            return normalize_content(result)
        except Exception as exc:
            if is_quota_exhausted(exc):
                _logger.warning("Anthropic quota exhausted: %s", exc)
            raise


class AnthropicClient(BaseLLMClient):
    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model, "streaming": True}
        # Opt-in (default on) prompt caching for the system prefix. Popped here
        # because it's our flag, not a ChatAnthropic constructor kwarg.
        prompt_caching = bool(self.kwargs.get("prompt_caching", True))

        # Determine API Key (NO .env lookup)
        api_key = self.kwargs.get("api_key")
        if not api_key:
            raise ValueError("API key for Anthropic is not set. Please provide it in your Profile or Settings.")
        llm_kwargs["api_key"] = api_key

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url
        for key in _PASSTHROUGH_KWARGS:
            if key == "api_key":
                continue
            if key not in self.kwargs:
                continue
            if key == "effort" and not _supports_effort(self.model):
                continue
            llm_kwargs[key] = self.kwargs[key]
        llm = NormalizedChatAnthropic(**llm_kwargs)
        llm.prompt_caching = prompt_caching
        return llm

    def validate_model(self) -> bool:
        return validate_model("anthropic", self.model)
