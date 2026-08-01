"""Context-aware, secret-safe telemetry for LangGraph tool failures.

``ToolNode.handle_tool_errors`` receives only the exception, not the tool call
that raised it.  Without a small wrapper around each call, the run log can say
only "Tool Failed" — which makes a vendor outage indistinguishable from an
invalid model argument or a code defect.  The wrapper below keeps the identity
in a task-local ``ContextVar`` until the ToolNode's error handler runs.

The handler deliberately keeps ToolNode's existing graceful behaviour: it
returns an error ``ToolMessage`` so the analyst can continue with another tool
or the data it already has.  It never retries an external tool here; data
vendor routing already owns vendor fallback and an extra blind retry can spend
rate-limit budget twice.
"""

from __future__ import annotations

import contextvars
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ToolCallContext:
    """The safe identifiers associated with one in-flight tool call."""

    tool: str
    analyst: str | None
    call_id: str | None

_active_tool_call: contextvars.ContextVar[ToolCallContext | None] = contextvars.ContextVar(
    "active_tool_call", default=None
)

_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_.:-]+")
_FALLBACK_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|api[_-]?secret|token|password|authorization|cookie)\b"
    r"\s*([:=])\s*(?:bearer\s+)?[^\s,;]+"
)

def _safe_identifier(value: Any, *, fallback: str = "unknown") -> str:
    """Make model-supplied tool names safe to display and use as metric labels."""
    if value is None:
        return fallback
    clean = _IDENTIFIER_RE.sub("_", str(value).strip())
    return clean[:96] or fallback

def safe_tool_error(exc: BaseException, *, limit: int = 300) -> str:
    """Return an error summary safe for both the database log and the LLM.

    The database log handler also redacts records, but ToolNode feeds this text
    back into the model.  Redacting before returning it prevents a provider or
    vendor exception containing credentials from crossing that boundary.
    """
    message = str(exc).strip()
    try:
        from backend.core.log_redaction import redact_text

        message = redact_text(message)
    except Exception:
        message = _FALLBACK_SECRET_RE.sub(r"\1\2***REDACTED***", message)
    message = _FALLBACK_SECRET_RE.sub(r"\1\2***REDACTED***", message)
    message = " ".join(message.split())
    return message[:limit] or type(exc).__name__

def _context_for_exception(exc: BaseException) -> ToolCallContext:
    context = _active_tool_call.get()
    if context is not None:
        return context

    return ToolCallContext(
        tool=_safe_identifier(getattr(exc, "tool_name", None)),
        analyst=None,
        call_id=None,
    )

def tool_error_handler(exc: Exception) -> str:
    """Log a contextual tool failure and return ToolNode's safe fallback text."""
    from backend.trading_agents.agents.runtime.resilience import _touch_activity, classify_error, log_event

    _touch_activity()
    context = _context_for_exception(exc)
    error = safe_tool_error(exc)
    error_type = classify_error(exc)
    log_event(
        "tool_error",
        level=logging.WARNING,
        tool=context.tool,
        analyst=context.analyst,
        call_id=context.call_id,
        error_type=error_type,
        action="continue_without_tool",
        error=error,
    )

    try:
        from backend.core import metrics

        metrics.TOOL_ERRORS.labels(tool_name=context.tool, error_type=error_type).inc()
    except Exception:
        pass

    return (
        f"Tool '{context.tool}' failed ({error}). Do not retry it automatically; "
        "use a different tool or continue your analysis with the data already gathered."
    )

def make_async_tool_call_wrapper(analyst: str) -> Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]:
    """Build a ToolNode ``awrap_tool_call`` callback scoped to one analyst."""

    safe_analyst = _safe_identifier(analyst)

    async def wrapped(request: Any, execute: Callable[[Any], Awaitable[Any]]) -> Any:
        call = getattr(request, "tool_call", {}) or {}
        context = ToolCallContext(
            tool=_safe_identifier(call.get("name") if isinstance(call, dict) else None),
            analyst=safe_analyst,
            call_id=_safe_identifier(call.get("id") if isinstance(call, dict) else None, fallback="") or None,
        )
        token = _active_tool_call.set(context)
        try:
            return await execute(request)
        finally:
            _active_tool_call.reset(token)

    return wrapped

def pending_tool_calls(state: Any) -> list[dict[str, str]]:
    """Return safe ``name``/``id`` pairs for the ToolNode currently executing."""
    if not isinstance(state, dict):
        return []
    messages = state.get("messages") or []
    if not messages:
        return []
    last = messages[-1]
    calls = getattr(last, "tool_calls", None)
    if calls is None and isinstance(last, dict):
        calls = last.get("tool_calls")
    if not isinstance(calls, list):
        return []

    pending: list[dict[str, str]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        tool = _safe_identifier(call.get("name"))
        call_id = _safe_identifier(call.get("id"), fallback="")
        if call_id:
            pending.append({"name": tool, "id": call_id})
    return pending

def tool_timeout_messages(state: Any, timeout_seconds: float) -> list[Any]:
    """Build one valid error response for every timed-out tool call.

    A model that issued N tool calls must receive N matching ``ToolMessage``
    responses.  Returning one unaddressed dictionary after a batch timeout
    leaves the conversation invalid for providers that require a response per
    tool call.
    """
    from langchain_core.messages import ToolMessage

    content = f"Tool timed out after {timeout_seconds:g}s. Try a simpler query or another tool."
    return [
        ToolMessage(content=content, name=call["name"], tool_call_id=call["id"], status="error")
        for call in pending_tool_calls(state)
    ]

def log_tool_timeout(state: Any, *, analyst: str, timeout_seconds: float) -> list[Any]:
    """Record a batch timeout with the affected calls, then build fallbacks."""
    from backend.trading_agents.agents.runtime.resilience import log_event

    calls = pending_tool_calls(state)
    names = [call["name"] for call in calls] or ["unknown"]
    error = f"Timed out after {timeout_seconds:g}s"
    log_event(
        "tool_timeout",
        level=logging.WARNING,
        tool=names[0] if len(names) == 1 else None,
        tools=names,
        analyst=_safe_identifier(analyst),
        error_type="timeout",
        action="continue_without_tool",
        timeout_seconds=round(float(timeout_seconds), 1),
        error=error,
    )
    try:
        from backend.core import metrics

        for name in names:
            metrics.TOOL_ERRORS.labels(tool_name=name, error_type="timeout").inc()
    except Exception:
        pass
    return tool_timeout_messages(state, timeout_seconds)
