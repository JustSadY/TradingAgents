import re
from typing import Any

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

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
    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        result = await super().ainvoke(input, config, **kwargs)
        return normalize_content(result)


class AnthropicClient(BaseLLMClient):
    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model, "streaming": True}

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
        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("anthropic", self.model)
