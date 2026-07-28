import asyncio
import logging
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    """Mutable accumulator for per-call token usage across providers."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens

    @classmethod
    def from_response(cls, response: Any) -> "TokenUsage":
        """Extract token usage from a LangChain LLM response."""
        usage_meta = getattr(response, "usage_metadata", None) or {}
        return cls(
            input_tokens=usage_meta.get("input_tokens", 0),
            output_tokens=usage_meta.get("output_tokens", 0),
            total_tokens=usage_meta.get("total_tokens", 0),
        )


class TokenUsageTracker:
    """Per-analysis token usage accumulator.

    Tracks input/output/total tokens across all LLM calls in a single
    analysis run.  Thread-safe when used within a single async context.
    """

    def __init__(self) -> None:
        self.total: TokenUsage = TokenUsage()
        self._call_count: int = 0

    def record(self, response: Any) -> None:
        usage = TokenUsage.from_response(response)
        self.total.add(usage)
        self._call_count += 1

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset(self) -> None:
        self.total = TokenUsage()
        self._call_count = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "input_tokens": self.total.input_tokens,
            "output_tokens": self.total.output_tokens,
            "total_tokens": self.total.total_tokens,
            "llm_calls": self._call_count,
        }


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def is_quota_exhausted(exc: Exception) -> bool:
    """Detect permanent quota/resource exhaustion across providers.

    When a quota-exhausted error is detected the caller should fall back
    immediately instead of wasting retries that will also fail.
    """
    err_msg = str(exc).lower()
    signals = [
        "resourceexhausted",
        "insufficient_quota",
        "rate_limit_exceeded",
        "rate limit",
        "quota",
        "429",
        "too many requests",
    ]
    return any(signal in err_msg for signal in signals)


def is_rate_limited(exc: Exception) -> bool:
    """Detect transient rate-limit errors that may succeed on retry."""
    err_msg = str(exc).lower()
    signals = [
        "429",
        "rate_limit",
        "rate limit",
        "too many requests",
        "try again later",
        "retry after",
    ]
    return any(signal in err_msg for signal in signals)


def is_provider_function_degraded(exc: BaseException) -> bool:
    """Return whether a hosted model deployment has been marked unavailable.

    NVIDIA NIM exposes a model deployment as an NVCF ``Function``.  When its
    health check marks that function ``DEGRADED``, the API answers with HTTP
    400 even though this is a temporary provider-side outage, not a malformed
    request.  Matching the complete error shape keeps an arbitrary user/model
    response containing the word ``degraded`` from changing retry behaviour.
    """
    err_msg = str(exc).lower()
    return "degraded function cannot be invoked" in err_msg or (
        "function id" in err_msg and "degraded" in err_msg and "cannot be invoked" in err_msg
    )


def classify_error(exc: Exception) -> str:
    """Classify an LLM error into a category for structured handling.

    Returns one of ``quota_exhausted``, ``rate_limited``, ``auth``,
    ``timeout``, ``provider_degraded``, or ``unknown``.
    """
    err_msg = str(exc).lower()
    if is_provider_function_degraded(exc):
        return "provider_degraded"
    if is_quota_exhausted(exc):
        return "quota_exhausted"
    if is_rate_limited(exc):
        return "rate_limited"
    auth_signals = ["401", "403", "unauthorized", "forbidden", "invalid_api_key", "authentication"]
    if any(s in err_msg for s in auth_signals):
        return "auth"
    timeout_signals = ["timeout", "timed out", "deadline exceeded"]
    if any(s in err_msg for s in timeout_signals):
        return "timeout"
    return "unknown"


# ---------------------------------------------------------------------------
# Retry helper for rate-limited calls
# ---------------------------------------------------------------------------


async def retry_with_exponential_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """Await *coro_factory()*, retrying on rate-limit errors with backoff.

    Parameters
    ----------
    coro_factory:
        Zero-argument callable that returns an awaitable.  Called on each
        attempt so a fresh underlying connection / iterator is used.
    max_retries:
        How many times to retry before giving up (default 3).
    base_delay:
        Initial delay in seconds (doubles each retry, default 1.0).
    max_delay:
        Cap for the backoff delay (default 30.0).

    Returns
    -------
    The first successful result.

    Raises
    ------
    The last exception encountered (quota, auth, unknown, and degraded-provider
    errors are not retried).
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            category = classify_error(exc)
            if category in ("quota_exhausted", "auth", "provider_degraded", "unknown"):
                raise
            # rate_limited or timeout — retry
            delay = min(base_delay * (2**attempt), max_delay)
            logger.info(
                "LLM call %s (attempt %d/%d), retrying in %.1fs: %s",
                category,
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise last_exc


# ---------------------------------------------------------------------------
# Content normalisation
# ---------------------------------------------------------------------------


def normalize_content(response):
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "")
            if isinstance(item, dict) and item.get("type") == "text"
            else item
            if isinstance(item, str)
            else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


# ---------------------------------------------------------------------------
# Base client contract
# ---------------------------------------------------------------------------


class BaseLLMClient(ABC):
    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        if self.validate_model():
            return
        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        pass
