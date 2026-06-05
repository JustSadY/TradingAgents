"""Engine resilience + dedicated run logging.

Gives the multi-agent run its own structured log stream (the ``tradingagents.run``
logger, which the backend's DB log handler persists and surfaces under
``/api/logs``) and makes individual agent/tool failures non-fatal:

* a failing **tool** falls through — its error is logged and returned to the LLM
  as a message so the agent can try another tool or proceed (see
  ``tool_error_handler``, wired into every ``ToolNode``);
* a failing **agent/node** is retried with exponential backoff and, if it still
  fails, is skipped with a safe fallback instead of aborting the whole analysis
  (see ``retry_call`` and ``guard_node``).

Everything degrades gracefully: with no run context, no transient error and no
config overrides, behaviour is identical to before — these helpers only change
what happens *on failure*.
"""
from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Callable, Optional

# Dedicated run-log stream. Filter logs by this logger name to get the
# per-agent / per-tool execution trace.
run_logger = logging.getLogger("tradingagents.run")

# Substrings that mark an error as worth retrying (rate limits, timeouts, 5xx…).
_TRANSIENT_HINTS = (
    "rate limit", "ratelimit", "429", "timeout", "timed out", "temporar",
    "overload", "503", "502", "500", "connection", "unavailable", "again",
)


def _cfg(key: str, default):
    try:
        from backend.trading_agents.dataflows.config import get_config
        value = get_config().get(key, default)
        return value if value is not None else default
    except Exception:
        return default


def log_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    """Emit one structured run event to the dedicated run logger."""
    payload = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    run_logger.log(level, "run_event %s", payload)


def is_transient(exc: BaseException) -> bool:
    return any(hint in str(exc).lower() for hint in _TRANSIENT_HINTS)


async def retry_call(
    fn: Callable[[], Any],
    *,
    label: str,
    attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    retry_all: bool = True,
    run_in_thread: bool = False,
) -> Any:
    """Call ``fn`` with retries + exponential backoff.

    ``attempts`` is the total number of tries (default from config
    ``node_retry_attempts`` = 2). By default every exception is retried; set
    ``retry_all=False`` to only retry errors that look transient.
    """
    attempts = int(attempts if attempts is not None else _cfg("node_retry_attempts", 2))
    base_delay = float(base_delay if base_delay is not None else _cfg("node_retry_base_delay", 1.0))
    attempts = max(1, attempts)
    last: Optional[BaseException] = None
    import inspect
    import asyncio
    for i in range(attempts):
        try:
            if run_in_thread:
                return await asyncio.to_thread(fn)
            else:
                res = fn()
                if inspect.iscoroutine(res):
                    return await res
                return res
        except Exception as exc:  # noqa: BLE001 — deliberately broad for resilience
            last = exc
            is_last = i + 1 >= attempts
            if is_last or (not retry_all and not is_transient(exc)):
                break
            delay = base_delay * (2 ** i)
            log_event(
                "retry", level=logging.WARNING, label=label,
                attempt=i + 1, attempts=attempts, delay=round(delay, 1),
                error=str(exc)[:200],
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last


def tool_error_handler(exc: Exception) -> str:
    """``ToolNode`` error handler: log the failure and hand the LLM a message it
    can act on, so a failing tool falls through to the next one."""
    log_event("tool_error", level=logging.WARNING, error=str(exc)[:300])
    return (
        f"⚠️ This tool failed ({exc}). Do not retry it; use a different tool or "
        "continue your analysis with the data already gathered."
    )


def guard_node(
    fn: Callable,
    *,
    name: str,
    kind: str = "agent",
    fallback: Optional[Callable[[dict, BaseException], dict]] = None,
) -> Callable:
    """Wrap a graph node so it retries on failure, logs start/end/error, and —
    if it still fails — returns ``fallback(state, exc)`` (a safe partial state
    update) instead of aborting the run. With no ``fallback`` the error is
    logged and re-raised (previous behaviour)."""
    import inspect
    import asyncio

    async def wrapped(state, *args, **kwargs):
        start = time.time()
        # NOTE: the enable/disable kill-switch is owned by the AgentHierarchy and
        # enforced inside each Main Agent node (and by Market Intelligence when it
        # selects analyst sub-agents). guard_node intentionally does NOT re-check
        # enablement here — that would short-circuit before the cascade-aware
        # hierarchy logic runs and emit a different, less complete stub.
        log_event("node_start", node=name, kind=kind)
        try:
            is_async = inspect.iscoroutinefunction(fn)
            if is_async:
                result = await retry_call(
                    lambda: fn(state, *args, **kwargs),
                    label=f"{kind}:{name}",
                    run_in_thread=False,
                )
            else:
                result = await retry_call(
                    lambda: fn(state, *args, **kwargs),
                    label=f"{kind}:{name}",
                    run_in_thread=True,
                )
            log_event("node_end", node=name, kind=kind, ms=int((time.time() - start) * 1000))
            return result
        except Exception as exc:  # noqa: BLE001
            log_event(
                "node_error", level=logging.ERROR, node=name, kind=kind,
                error=str(exc)[:300], traceback=traceback.format_exc()[-700:],
            )
            if fallback is None:
                raise
            try:
                if inspect.iscoroutinefunction(fallback):
                    update = await fallback(state, exc)
                else:
                    update = fallback(state, exc)
            except Exception as fb_exc:  # noqa: BLE001 — never let the fallback abort
                log_event("fallback_error", level=logging.ERROR, node=name, error=str(fb_exc)[:200])
                raise exc from fb_exc
            log_event("node_skipped", level=logging.WARNING, node=name, kind=kind)
            return update

    wrapped.__name__ = getattr(fn, "__name__", name)
    return wrapped
