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
from collections.abc import Callable
from typing import Any

# Dedicated run-log stream. Filter logs by this logger name to get the
# per-agent / per-tool execution trace.
run_logger = logging.getLogger("tradingagents.run")

# Substrings that mark an error as worth retrying (rate limits, timeouts, 5xx…).
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


def _cfg(key: str, default, runtime_config: dict | None = None):
    try:
        if isinstance(runtime_config, dict):
            value = runtime_config.get(key, default)
            return value if value is not None else default
        from backend.trading_agents.dataflows.config import get_config

        value = get_config().get(key, default)
        return value if value is not None else default
    except Exception:
        return default


def _metrics():
    """Prometheus metrics module, or None — metrics must never break a run."""
    try:
        from backend.core import metrics

        return metrics
    except Exception:
        return None


def log_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    """Emit one structured run event to the dedicated run logger."""
    payload = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    run_logger.log(level, "run_event %s", payload)


def is_transient(exc: BaseException) -> bool:
    return any(hint in str(exc).lower() for hint in _TRANSIENT_HINTS)


async def _execute_fn(fn: Callable[[], Any], run_in_thread: bool) -> Any:
    import asyncio
    import inspect

    if run_in_thread:
        return await asyncio.to_thread(fn)
    res = fn()
    if inspect.iscoroutine(res):
        return await res
    return res


async def retry_call(
    fn: Callable[[], Any],
    *,
    label: str,
    attempts: int | None = None,
    base_delay: float | None = None,
    retry_all: bool = True,
    run_in_thread: bool = False,
    runtime_config: dict | None = None,
) -> Any:
    """Call ``fn`` with retries + exponential backoff.

    ``attempts`` is the total number of tries (default from config
    ``node_retry_attempts`` = 2). By default every exception is retried; set
    ``retry_all=False`` to only retry errors that look transient.
    """
    attempts = int(attempts if attempts is not None else _cfg("node_retry_attempts", 2, runtime_config))
    base_delay = float(base_delay if base_delay is not None else _cfg("node_retry_base_delay", 1.0, runtime_config))
    attempts = max(1, attempts)
    last: BaseException | None = None
    import asyncio

    for i in range(attempts):
        try:
            return await _execute_fn(fn, run_in_thread)
        except Exception as exc:  # noqa: BLE001 — deliberately broad for resilience
            last = exc
            if i + 1 >= attempts or (not retry_all and not is_transient(exc)):
                break

            delay = base_delay * (2**i)
            _log_retry_metrics(label, i, attempts, delay, exc)
            await _emit_retry_progress(label, i, attempts, exc)
            await asyncio.sleep(delay)

    assert last is not None
    raise last


def _log_retry_metrics(label: str, i: int, attempts: int, delay: float, exc: Exception):
    log_event(
        "retry",
        level=logging.WARNING,
        label=label,
        attempt=i + 1,
        attempts=attempts,
        delay=round(delay, 1),
        error=str(exc)[:200],
    )
    m = _metrics()
    if m:
        m.NODE_RETRIES.labels(label=label).inc()


async def _emit_retry_progress(label: str, i: int, attempts: int, exc: Exception):
    from backend.trading_agents.agents.data.chart_tools import active_run_context

    ctx = active_run_context.get(None)
    if not ctx or "emitter" not in ctx:
        return

    try:
        emitter = ctx["emitter"]
        clean_label = label.replace("analyst:", "").replace("main:", "").title()
        err_msg = str(exc)
        if "429" in err_msg or "rate_limit" in err_msg.lower() or "rate limit" in err_msg.lower():
            err_msg = "Rate limit (429) detected"
        elif "503" in err_msg or "service unavailable" in err_msg.lower():
            err_msg = "Service unavailable (503)"
        else:
            err_msg = err_msg[:60]

        warning_msg = f"Warning: Retrying {clean_label} (Attempt {i + 1}/{attempts}) due to: {err_msg}"
        await emitter.emit(
            {
                "type": "progress",
                "node": label,
                "label": warning_msg,
                "stage": "warning",
            }
        )
    except Exception:
        pass


def tool_error_handler(exc: Exception) -> str:
    """``ToolNode`` error handler: log the failure and hand the LLM a message it
    can act on, so a failing tool falls through to the next one."""
    log_event("tool_error", level=logging.WARNING, error=str(exc)[:300])
    return (
        f"This tool failed ({exc}). Do not retry it; use a different tool or "
        "continue your analysis with the data already gathered."
    )


def guard_node(
    fn: Callable,
    *,
    name: str,
    kind: str = "agent",
    fallback: Callable[[dict, BaseException], dict] | None = None,
) -> Callable:
    """Wrap a graph node so it retries on failure, logs start/end/error, and —
    if it still fails — returns ``fallback(state, exc)`` (a safe partial state
    update) instead of aborting the run. With no ``fallback`` the error is
    logged and re-raised (previous behaviour)."""
    import inspect

    async def wrapped(state, *args, **kwargs):
        start = time.time()
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
            _log_node_success(name, kind, start)
            return result
        except Exception as exc:  # noqa: BLE001
            _log_node_error(name, kind, exc)
            if fallback is None:
                raise
            return await _handle_node_fallback(name, kind, fallback, state, exc)

    wrapped.__name__ = getattr(fn, "__name__", name)
    return wrapped


def _log_node_success(name: str, kind: str, start_time: float):
    ms = int((time.time() - start_time) * 1000)
    log_event("node_end", node=name, kind=kind, ms=ms)
    m = _metrics()
    if m:
        m.NODE_DURATION.labels(node=name, kind=kind).observe(time.time() - start_time)


def _log_node_error(name: str, kind: str, exc: Exception):
    log_event(
        "node_error",
        level=logging.ERROR,
        node=name,
        kind=kind,
        error=str(exc)[:300],
        traceback=traceback.format_exc()[-700:],
    )
    m = _metrics()
    if m:
        m.NODE_ERRORS.labels(node=name, kind=kind).inc()


async def _handle_node_fallback(name: str, kind: str, fallback: Callable, state: dict, exc: Exception) -> dict:
    import inspect

    try:
        if inspect.iscoroutinefunction(fallback):
            update = await fallback(state, exc)
        else:
            update = fallback(state, exc)
    except Exception as fb_exc:  # noqa: BLE001 — never let the fallback abort
        log_event("fallback_error", level=logging.ERROR, node=name, error=str(fb_exc)[:200])
        raise exc from fb_exc

    log_event("node_skipped", level=logging.WARNING, node=name, kind=kind)
    m = _metrics()
    if m:
        m.NODE_FALLBACKS.labels(node=name, kind=kind).inc()
    return update
