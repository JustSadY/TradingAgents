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

import contextvars
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
    "resourceexhausted",
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

# ---- Circuit breaker state ----
# Maps node/agent name → {"failures": int, "open_since": float | None}
# Module-level so it persists for the lifetime of the process.
_circuit_state: dict[str, dict] = {}


def _circuit_key(name: str, kind: str) -> str:
    return f"{kind}:{name}"


# ---- Per-run report card ----
# ContextVar so concurrent analysis runs don't clobber each other's data.
# Each value is a dict: {agent_key: {"retries": int, "fallback": bool, "error": str | None}}
_run_report_card: contextvars.ContextVar[dict[str, dict] | None] = contextvars.ContextVar(
    "agent_report_card", default=None
)


def init_report_card() -> dict[str, dict]:
    """Create (or reset) the per-run report card and return it."""
    card: dict[str, dict] = {}
    _run_report_card.set(card)
    return card


def get_report_card() -> dict[str, dict]:
    card = _run_report_card.get()
    if card is None:
        card = init_report_card()
    return card


def record_agent_result(agent_key: str, *, retries: int = 0, fallback: bool = False, error: str | None = None) -> None:
    card = get_report_card()
    card[agent_key] = {"retries": retries, "fallback": fallback, "error": error[:200] if error else None}


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


def classify_error(exc: BaseException) -> str:
    """Classify an exception into a high-level error category.

    Returns one of ``"auth"``, ``"quota"``, ``"timeout"``, ``"transient"``,
    or ``"bug"``. Used for Prometheus label cardinality and post-run
    diagnostics.
    """
    msg = str(exc).lower()
    if any(k in msg for k in ("401", "unauthorized", "invalid api key", "auth")):
        return "auth"
    if any(k in msg for k in ("429", "quota", "rate limit", "ratelimit", "rate_limit")):
        return "quota"
    if any(k in msg for k in ("timeout", "timed out", "deadline")):
        return "timeout"
    if is_transient(exc):
        return "transient"
    return "bug"


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
    timeout: float | None = None,
    retry_all: bool = True,
    run_in_thread: bool = False,
    runtime_config: dict | None = None,
) -> Any:
    """Call ``fn`` with retries + exponential backoff.

    ``attempts`` is the total number of tries (default from config
    ``node_retry_attempts`` = 2). By default every exception is retried; set
    ``retry_all=False`` to only retry errors that look transient.

    ``timeout`` wraps each invocation in ``asyncio.wait_for`` so a hung
    provider can't stall the run. Timeouts are treated as transient errors
    and feed into the retry path.
    """
    attempts = int(attempts if attempts is not None else _cfg("node_retry_attempts", 2, runtime_config))
    base_delay = float(base_delay if base_delay is not None else _cfg("node_retry_base_delay", 1.0, runtime_config))
    timeout = float(timeout) if timeout is not None else _cfg("node_timeout_seconds", 120, runtime_config)
    attempts = max(1, attempts)
    last: BaseException | None = None
    import asyncio

    for i in range(attempts):
        try:
            coro = _execute_fn(fn, run_in_thread)
            return await asyncio.wait_for(coro, timeout=timeout)
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
        if "429" in err_msg or "rate_limit" in err_msg.lower() or "rate limit" in err_msg.lower() or "resourceexhausted" in err_msg.lower():
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
        await emitter.emit_retry(clean_label, i + 1, attempts, err_msg)
    except Exception:
        pass


def tool_error_handler(exc: Exception) -> str:
    """``ToolNode`` error handler: log the failure and hand the LLM a message it
    can act on, so a failing tool falls through to the next one."""
    log_event("tool_error", level=logging.WARNING, error=str(exc)[:300])
    m = _metrics()
    if m:
        m.TOOL_ERRORS.labels(tool_name="unknown", error_type=classify_error(exc)).inc()
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

        ck = _circuit_key(name, kind)
        cb = _circuit_state.get(ck)
        cb_threshold = _cfg("circuit_breaker_threshold", 3)
        cb_cooldown = _cfg("circuit_breaker_cooldown", 60)

        if cb and cb.get("open_since") is not None:
            elapsed = time.time() - cb["open_since"]
            if elapsed < cb_cooldown:
                log_event("circuit_open", level=logging.WARNING, node=name, kind=kind, elapsed_seconds=round(elapsed, 1))
                m = _metrics()
                if m:
                    m.NODE_CIRCUIT_OPEN.labels(node=name, kind=kind).inc()
                _emit_circuit_open_ws(name, kind, elapsed)
                record_agent_result(name, retries=cb_threshold, fallback=True, error=f"Circuit breaker open ({elapsed:.0f}s elapsed)")
                if fallback is None:
                    raise RuntimeError(f"Circuit breaker open for {name} — not retrying.")
                return await _handle_node_fallback(name, kind, fallback, state, RuntimeError(f"Circuit breaker open for {name}"))
            cb["open_since"] = None
            cb["failures"] = 0

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
            _circuit_state.pop(ck, None)
            _log_node_success(name, kind, start)
            return result
        except Exception as exc:  # noqa: BLE001
            await _log_node_error(name, kind, exc)
            entry = _circuit_state.setdefault(ck, {"failures": 0, "open_since": None})
            entry["failures"] += 1
            if entry["failures"] >= cb_threshold:
                entry["open_since"] = time.time()
                log_event("circuit_tripped", level=logging.WARNING, node=name, kind=kind, failures=entry["failures"])
            record_agent_result(name, retries=entry["failures"], fallback=fallback is not None, error=str(exc)[:200])
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


async def _log_node_error(name: str, kind: str, exc: Exception):
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
        m.NODE_ERRORS_BY_TYPE.labels(node=name, kind=kind, error_type=classify_error(exc)).inc()
    _emit_node_error_ws(name, kind, exc)


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
    _emit_fallback_ws(name, kind, exc)
    return update


def _emit_circuit_open_ws(node: str, kind: str, elapsed: float):
    """Fire-and-forget WS event for circuit-open state, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            import asyncio

            asyncio.create_task(ctx["emitter"].emit_circuit_open(node, kind, elapsed))
    except Exception:
        pass


def _emit_node_error_ws(node: str, kind: str, exc: Exception):
    """Fire-and-forget WS event for node error, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            import asyncio

            asyncio.create_task(
                ctx["emitter"].emit_node_error(node, kind, str(exc)[:200], classify_error(exc))
            )
    except Exception:
        pass


def _emit_fallback_ws(node: str, kind: str, exc: Exception):
    """Fire-and-forget WS event for fallback activation, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            import asyncio

            asyncio.create_task(ctx["emitter"].emit_fallback(node, kind, str(exc)[:200]))
    except Exception:
        pass
