import asyncio
import logging
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# --- Global LLM Concurrency Control ---
_GLOBAL_LLM_SEMAPHORE: asyncio.Semaphore | None = None
_GLOBAL_LLM_SEMAPHORE_LOCK = asyncio.Lock()
DEFAULT_GLOBAL_LLM_CONCURRENCY = 16


def get_global_llm_semaphore(limit: int = DEFAULT_GLOBAL_LLM_CONCURRENCY) -> asyncio.Semaphore:
    """Return the process-wide LLM concurrency semaphore.

    Caps concurrent active LLM HTTP requests across all subgraphs and agents to
    prevent provider worker request limits (e.g. 32/32) from being exceeded.
    """
    global _GLOBAL_LLM_SEMAPHORE
    if _GLOBAL_LLM_SEMAPHORE is None:
        _GLOBAL_LLM_SEMAPHORE = asyncio.Semaphore(limit)
    return _GLOBAL_LLM_SEMAPHORE


class global_llm_concurrency_guard:
    """Async context manager to throttle concurrent LLM requests globally."""

    def __init__(self, limit: int = DEFAULT_GLOBAL_LLM_CONCURRENCY):
        self.limit = limit

    async def __aenter__(self):
        sem = get_global_llm_semaphore(self.limit)
        await sem.acquire()
        return sem

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        sem = get_global_llm_semaphore(self.limit)
        sem.release()

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

_TRANSIENT_HINTS = (
    "rate limit",
    "ratelimit",
    "429",
    "timeout",
    "timed out",
    "temporar",
    "overload",
    "503",
    "502",
    "500",
    "connection",
    "unavailable",
    "again",
)

def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError))

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

# The node runtime (`retry_call`/`guard_node`) is the single retry authority.
# LangChain clients otherwise retry ~2 times of their own accord, which the app
# never configured and which multiplied with the node attempts and the provider
# fallback chain. Providers still get retried — once, where it is observable and
# where `node_retry_attempts` controls it.
SDK_RETRIES = 0

def is_transient(exc: BaseException) -> bool:
    """Whether an error is worth retrying with the same provider."""
    if _is_timeout_error(exc) or isinstance(exc, ConnectionError):
        return True
    return any(hint in str(exc).lower() for hint in _TRANSIENT_HINTS)

def classify_error(exc: BaseException) -> str:
    """Classify an exception into a high-level error category.

    Returns one of ``"auth"``, ``"quota"``, ``"timeout"``,
    ``"provider_degraded"``, ``"transient"`` or ``"bug"``.

    This is the single classifier for the whole engine. There used to be a
    second one in ``agents/runtime/resilience`` with a different vocabulary
    (``quota_exhausted``/``rate_limited``/``unknown``), so the same provider
    error was reported under two different names depending on which layer
    caught it. These category strings are the ones that reach Prometheus
    (``NODE_ERRORS_BY_TYPE``) and the analysis WebSocket, so they are the
    canonical set; changing one is an observable change.
    """
    msg = str(exc).lower()
    if is_provider_function_degraded(exc):
        return "provider_degraded"
    # Union of both former implementations. fallback.py treats "auth" as a
    # permanent failure and stops trying other providers, so dropping a signal
    # here would make an invalid key burn a call against every fallback.
    auth_signals = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "invalid_api_key",
        "invalid api key",
        "authentication",
        "auth",
    )
    if any(k in msg for k in auth_signals):
        return "auth"
    if is_quota_exhausted(exc) or is_rate_limited(exc):
        return "quota"
    if _is_timeout_error(exc) or any(k in msg for k in ("timeout", "timed out", "deadline")):
        return "timeout"
    if is_transient(exc):
        return "transient"
    return "bug"

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
