"""Engine resilience + dedicated run logging.

Gives the multi-agent run its own structured log stream (the ``tradingagents.run``
logger, which the backend's DB log handler persists and surfaces under
``/api/logs``) and makes individual agent/tool failures non-fatal:

* a failing **tool** falls through — its error is logged and returned to the LLM
  as a message so the agent can try another tool or proceed (see
  ``agents.runtime.tool_telemetry``, wired into every ``ToolNode``);
* a failing **agent/node** is retried with exponential backoff and, if it still
  fails, is skipped with a safe fallback instead of aborting the whole analysis
  (see ``retry_call`` and ``guard_node``).

Everything degrades gracefully: with no run context, no transient error and no
config overrides, behaviour is identical to before — these helpers only change
what happens *on failure*.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
import traceback
from collections.abc import Callable
from typing import Any

from backend.trading_agents.llm_clients.base_client import is_provider_function_degraded

run_logger = logging.getLogger("tradingagents.run")

_WS_BG_TASKS: set[asyncio.Task] = set()

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

_circuit_state: dict[str, dict] = {}

def _circuit_key(name: str, kind: str) -> str:
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None) or {}
        user_id = ctx.get("user_id")
        graph = ctx.get("graph")
        provider = getattr(graph, "llm_provider", None) if graph is not None else None
        if not provider and graph is not None:
            provider = (getattr(graph, "config", {}) or {}).get("llm_provider")
        return f"{kind}:{name}:user={user_id if user_id is not None else 'system'}:provider={provider or 'default'}"
    except Exception:
        return f"{kind}:{name}:user=unknown:provider=default"

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

def _active_runtime_config() -> dict | None:
    """Read graph config from the current task instead of process-global state."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None) or {}
        graph = ctx.get("graph")
        config = getattr(graph, "config", None)
        return config if isinstance(config, dict) else None
    except Exception:
        return None

def _touch_activity() -> None:
    """Record node/retry/tool lifecycle activity for this task, best-effort."""
    try:
        from backend.services.analysis.activity import touch_current_analysis

        touch_current_analysis()
    except Exception:
        return

def _message_type(message: Any) -> str:
    """Return a LangChain message type without requiring a concrete class.

    LangGraph keeps messages as ``BaseMessage`` instances in production, while
    isolated graph tests and older checkpoints can contain plain dictionaries.
    Lifecycle logging must be able to inspect both without making the graph
    depend on a particular LangChain release.
    """
    if isinstance(message, dict):
        value = message.get("type")
    else:
        value = getattr(message, "type", None)
    return str(value or "").lower()

def _message_has_tool_calls(message: Any) -> bool:
    """Whether *message* is an assistant request that opened a tool round."""
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    else:
        calls = getattr(message, "tool_calls", None)
    return bool(calls)

def _analyst_turn_fields(state: Any, kind: str) -> dict[str, Any]:
    """Describe one analyst invocation without altering its execution.

    An analyst subgraph deliberately has an ``agent -> ToolNode -> agent``
    loop.  The second and later agent calls are real LLM continuation turns:
    the model is reading tool results, not starting duplicate analysts.  The
    old lifecycle logs gave every turn the identical ``Start`` label, which
    made a normal multi-tool analysis appear to run the same analyst multiple
    times.

    Keep the stable ``node_start``/``node_end`` event names for consumers and
    Prometheus lifecycle metrics, but attach a small, bounded description for
    the UI.  Only a count is recorded; raw tool outputs never enter the run
    log through this path.
    """
    if kind != "analyst" or not isinstance(state, dict):
        return {}

    messages = state.get("messages")
    if not isinstance(messages, (list, tuple)) or not messages:
        return {"phase": "initial", "turn": 1}

    tool_results = 0
    for message in reversed(messages):
        if _message_type(message) != "tool":
            break
        tool_results += 1

    if not tool_results:
        return {"phase": "initial", "turn": 1}

    completed_rounds = sum(1 for message in messages if _message_has_tool_calls(message))
    return {
        "phase": "continuation",
        "turn": max(2, completed_rounds + 1),
        "tool_results": tool_results,
    }

def _is_timeout_error(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError))

def is_transient(exc: BaseException) -> bool:
    if _is_timeout_error(exc) or isinstance(exc, ConnectionError):
        return True
    return any(hint in str(exc).lower() for hint in _TRANSIENT_HINTS)

def classify_error(exc: BaseException) -> str:
    """Classify an exception into a high-level error category.

    Returns one of ``"auth"``, ``"quota"``, ``"timeout"``,
    ``"provider_degraded"``, ``"transient"``, or ``"bug"``. Used for
    Prometheus label cardinality and post-run diagnostics.
    """
    msg = str(exc).lower()
    if is_provider_function_degraded(exc):
        return "provider_degraded"
    if any(k in msg for k in ("401", "unauthorized", "invalid api key", "auth")):
        return "auth"
    if any(k in msg for k in ("429", "quota", "rate limit", "ratelimit", "rate_limit")):
        return "quota"
    if _is_timeout_error(exc) or any(k in msg for k in ("timeout", "timed out", "deadline")):
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
    timeout_multiplier: float = 1.0,
    retry_all: bool = False,
    retry_timeouts: bool = True,
    run_in_thread: bool = False,
    runtime_config: dict | None = None,
) -> Any:
    """Call ``fn`` with retries + exponential backoff.

    ``attempts`` is the total number of tries (default from config
    ``node_retry_attempts``).  By default only transient failures are retried;
    set ``retry_all=True`` only for an explicitly idempotent operation.

    ``timeout`` wraps each invocation in ``asyncio.wait_for`` so a hung
    provider can't stall the run. ``timeout_multiplier`` lets a coordinator
    own several bounded leaf calls without being cut off after the first one.
    Timeouts are transient by default; coordinators can set
    ``retry_timeouts=False`` so a partial multi-step run is not restarted.

    The inner ``_retry_llm_call`` or ``retry_call`` at the sub-agent level
    provides a finer-grained retry for transient LLM errors.
    """
    attempts = int(attempts if attempts is not None else _cfg("node_retry_attempts", 1, runtime_config))
    base_delay = float(base_delay if base_delay is not None else _cfg("node_retry_base_delay", 1.0, runtime_config))
    timeout_seconds = (
        float(timeout) if timeout is not None else float(_cfg("node_timeout_seconds", 120, runtime_config))
    )
    try:
        multiplier = float(timeout_multiplier)
    except (TypeError, ValueError):
        multiplier = 1.0
    timeout_seconds = max(0.0, timeout_seconds * max(0.0, multiplier))
    effective_timeout = timeout_seconds if timeout_seconds > 0 else None
    attempts = max(1, attempts)
    last: BaseException | None = None
    import asyncio

    for i in range(attempts):
        try:
            _touch_activity()
            coro = _execute_fn(fn, run_in_thread)
            if effective_timeout is None:
                return await coro
            return await asyncio.wait_for(coro, timeout=effective_timeout)
        except Exception as exc:
            last = exc
            err_msg = str(exc).lower()
            if "quota exhausted" in err_msg:
                break
            if "resourceexhausted" in err_msg and ("total" in err_msg or "quota" in err_msg):
                break
            if is_provider_function_degraded(exc):
                break
            if _is_timeout_error(exc) and not retry_timeouts:
                break
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
        low = err_msg.lower()
        if "resourceexhausted" in low and ("total" in low or "quota" in low):
            err_msg = "Quota exhausted — skipping retries"
        elif "429" in err_msg or "rate_limit" in low or "rate limit" in low:
            err_msg = "Rate limit (429) detected"
        elif "503" in err_msg or "service unavailable" in low:
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

def guard_node(
    fn: Callable,
    *,
    name: str,
    kind: str = "agent",
    fallback: Callable[[dict, BaseException], dict] | None = None,
    timeout_multiplier: float = 1.0,
    retry_timeouts: bool = True,
) -> Callable:
    """Wrap a graph node so it retries on failure, logs start/end/error, and —
    if it still fails — returns ``fallback(state, exc)`` (a safe partial state
    update) instead of aborting the run. With no ``fallback`` the error is
    logged and re-raised (previous behaviour)."""
    import inspect

    async def wrapped(state, *args, **kwargs):
        start = time.time()
        _touch_activity()
        turn_fields = _analyst_turn_fields(state, kind)
        log_event("node_start", node=name, kind=kind, **turn_fields)

        runtime_config = _active_runtime_config()
        ck = _circuit_key(name, kind)
        cb = _circuit_state.get(ck)
        cb_threshold = _cfg("circuit_breaker_threshold", 3, runtime_config)
        cb_cooldown = _cfg("circuit_breaker_cooldown", 60, runtime_config)

        if cb and cb.get("open_since") is not None:
            elapsed = time.time() - cb["open_since"]
            if elapsed < cb_cooldown:
                log_event(
                    "circuit_open", level=logging.WARNING, node=name, kind=kind, elapsed_seconds=round(elapsed, 1)
                )
                m = _metrics()
                if m:
                    m.NODE_CIRCUIT_OPEN.labels(node=name, kind=kind).inc()
                _emit_circuit_open_ws(name, kind, elapsed)
                record_agent_result(
                    name, retries=cb_threshold, fallback=True, error=f"Circuit breaker open ({elapsed:.0f}s elapsed)"
                )
                if fallback is None:
                    raise RuntimeError(f"Circuit breaker open for {name} — not retrying.")
                return await _handle_node_fallback(
                    name, kind, fallback, state, RuntimeError(f"Circuit breaker open for {name}")
                )
            cb["open_since"] = None
            cb["failures"] = 0

        try:
            is_async = inspect.iscoroutinefunction(fn)
            if is_async:
                result = await retry_call(
                    lambda: fn(state, *args, **kwargs),
                    label=f"{kind}:{name}",
                    run_in_thread=False,
                    timeout_multiplier=timeout_multiplier,
                    retry_all=False,
                    retry_timeouts=retry_timeouts,
                    runtime_config=runtime_config,
                )
            else:
                result = await retry_call(
                    lambda: fn(state, *args, **kwargs),
                    label=f"{kind}:{name}",
                    run_in_thread=True,
                    timeout_multiplier=timeout_multiplier,
                    retry_all=False,
                    retry_timeouts=retry_timeouts,
                    runtime_config=runtime_config,
                )
            _circuit_state.pop(ck, None)
            _log_node_success(name, kind, start, **turn_fields)
            return result
        except Exception as exc:
            await _log_node_error(name, kind, exc, **turn_fields)
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

def _log_node_success(name: str, kind: str, start_time: float, **turn_fields: Any):
    ms = int((time.time() - start_time) * 1000)
    log_event("node_end", node=name, kind=kind, ms=ms, **turn_fields)
    m = _metrics()
    if m:
        m.NODE_DURATION.labels(node=name, kind=kind).observe(time.time() - start_time)

async def _log_node_error(name: str, kind: str, exc: Exception, **turn_fields: Any):
    log_event(
        "node_error",
        level=logging.ERROR,
        node=name,
        kind=kind,
        **turn_fields,
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
    except Exception as fb_exc:
        log_event("fallback_error", level=logging.ERROR, node=name, error=str(fb_exc)[:200])
        raise exc from fb_exc

    log_event("node_skipped", level=logging.WARNING, node=name, kind=kind)
    m = _metrics()
    if m:
        m.NODE_FALLBACKS.labels(node=name, kind=kind).inc()
    _emit_fallback_ws(name, kind, exc)
    return update

def _spawn_ws_task(coro):
    """Create a tracked fire-and-forget WS task so GC doesn't collect it mid-flight."""
    task = asyncio.create_task(coro)
    _WS_BG_TASKS.add(task)
    task.add_done_callback(_WS_BG_TASKS.discard)
    return task

def _emit_circuit_open_ws(node: str, kind: str, elapsed: float):
    """Fire-and-forget WS event for circuit-open state, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            _spawn_ws_task(ctx["emitter"].emit_circuit_open(node, kind, elapsed))
    except Exception:
        pass

def _emit_node_error_ws(node: str, kind: str, exc: Exception):
    """Fire-and-forget WS event for node error, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            _spawn_ws_task(ctx["emitter"].emit_node_error(node, kind, str(exc)[:200], classify_error(exc)))
    except Exception:
        pass

def _emit_fallback_ws(node: str, kind: str, exc: Exception):
    """Fire-and-forget WS event for fallback activation, best-effort."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            _spawn_ws_task(ctx["emitter"].emit_fallback(node, kind, str(exc)[:200]))
    except Exception:
        pass
