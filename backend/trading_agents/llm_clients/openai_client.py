import logging
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, is_quota_exhausted, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model

logger = logging.getLogger(__name__)


def _strip_chunk_usage(chunk) -> Any | None:
    """Remove (and return) the usage_metadata carried by a streamed chunk."""
    message = getattr(chunk, "message", None)
    usage = getattr(message, "usage_metadata", None) if message is not None else None
    if usage:
        message.usage_metadata = None

    response_metadata = getattr(message, "response_metadata", None) if message is not None else None
    if isinstance(response_metadata, dict):
        for key in ("token_usage", "usage"):
            if key in response_metadata:
                if usage is None:
                    usage = response_metadata[key]
                del response_metadata[key]

    generation_info = getattr(chunk, "generation_info", None)
    if isinstance(generation_info, dict):
        for key in ("token_usage", "usage"):
            if key in generation_info:
                if usage is None:
                    usage = generation_info[key]
                del generation_info[key]

    return usage or None


def _final_usage_chunk(usage) -> ChatGenerationChunk:
    return ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage))


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content and sane streamed token usage.

    LangChain SUMS usage_metadata when merging stream chunks. Real OpenAI sends
    usage once (final chunk), so the sum is correct — but several
    OpenAI-compatible providers (DeepSeek/Qwen/GLM/LiteLLM proxies, …) emit
    CUMULATIVE usage on every chunk, so the merged total becomes
    input_tokens × chunk_count and the per-analysis counters explode into the
    billions. We strip per-chunk usage and re-emit only the LAST snapshot at
    the end of the stream, which is correct for both behaviours (cumulative →
    last snapshot is the total; final-only → last snapshot is the only one).

    Quota exhaustion: detects ``ResourceExhausted`` + ``total``/``quota``
    errors from the provider and logs them. The exception propagates so the
    calling retry wrapper (``_retry_llm_call`` / ``retry_call`` / ``_safe``)
    can fall back immediately without burning quota on retries.
    """

    def _stream(self, *args, **kwargs):
        last_usage = None
        try:
            for chunk in super()._stream(*args, **kwargs):
                usage = _strip_chunk_usage(chunk)
                if usage is not None:
                    last_usage = usage
                yield chunk
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Quota exhausted: %s", exc)
            raise
        if last_usage is not None:
            yield _final_usage_chunk(last_usage)

    async def _astream(self, *args, **kwargs):
        last_usage = None
        try:
            async for chunk in super()._astream(*args, **kwargs):
                usage = _strip_chunk_usage(chunk)
                if usage is not None:
                    last_usage = usage
                yield chunk
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Quota exhausted: %s", exc)
            raise
        if last_usage is not None:
            yield _final_usage_chunk(last_usage)

    def invoke(self, input, config=None, **kwargs):
        try:
            return normalize_content(super().invoke(input, config, **kwargs))
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Quota exhausted: %s", exc)
            raise

    async def ainvoke(self, input, config=None, **kwargs):
        try:
            result = await super().ainvoke(input, config, **kwargs)
            return normalize_content(result)
        except Exception as exc:
            if is_quota_exhausted(exc):
                logger.warning("Quota exhausted: %s", exc)
            raise

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
    "temperature",
    "max_tokens",
    "top_p",
    "stop",
    "frequency_penalty",
    "presence_penalty",
)

_PROVIDER_BASE_URL = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

_OLLAMA_PROVIDER = "ollama"


def get_ollama_base_url() -> str:
    """Return the server-owned OpenAI-compatible Ollama endpoint."""
    from backend.core.config import get_settings

    base_url = get_settings().OLLAMA_BASE_URL.rstrip("/")
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        provider: str = "openai",
        **kwargs,
    ):
        self.provider = provider.lower()
        if self.provider == _OLLAMA_PROVIDER:
            # A local model endpoint is infrastructure configuration, not a
            # tenant credential. Drop stale URL/key values before they can
            # re-enter the LLM runtime through a direct library caller.
            base_url = None
            kwargs.pop("api_key", None)
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        # stream_usage makes OpenAI include token usage in streamed responses;
        # without it every streaming call reports no usage and the per-analysis
        # token counters silently stay at zero.
        llm_kwargs = {"model": self.model, "streaming": True, "stream_usage": True}

        if self.provider == _OLLAMA_PROVIDER:
            # Ollama ignores this sentinel, but ChatOpenAI requires a value.
            llm_kwargs["base_url"] = get_ollama_base_url()
            llm_kwargs["api_key"] = _OLLAMA_PROVIDER
        else:
            resolved_base_url = self.base_url or _PROVIDER_BASE_URL.get(self.provider)
            if resolved_base_url:
                llm_kwargs["base_url"] = resolved_base_url

            api_key = self.kwargs.get("api_key")
            if not api_key:
                raise ValueError(
                    f"API key for provider '{self.provider}' is not set. Please provide it in your Profile or Settings."
                )
            llm_kwargs["api_key"] = api_key

        for key in _PASSTHROUGH_KWARGS:
            # ``api_key`` is resolved by the provider contract above and must
            # never be overwritten by the generic passthrough.
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

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
