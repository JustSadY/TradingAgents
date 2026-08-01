"""Invocation-time provider failover for chat models.

``Runnable.with_fallbacks`` cannot be applied to a chat model up front: the
resulting wrapper is not a ``BaseChatModel``, so ``bind_tools`` and
``with_structured_output`` — both required by the agent nodes — disappear.
``FallbackLLM`` keeps the chat-model surface by applying those transformations
to the primary and every fallback separately, combining the results with
``with_fallbacks`` only at the Runnable boundary.

Supports a multi-level fallback chain::

    FallbackLLM(primary, [fb_a, fb_b, fb_c])

The chain is tried in order — if the primary raises, ``fb_a``; if ``fb_a``
also raises, ``fb_b``; and so on.
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import classify_error

logger = logging.getLogger(__name__)

def _is_permanent_failure(exc: Exception) -> bool:
    """Check if an exception indicates a permanent failure that would also
    affect fallback providers (e.g. invalid API key format).

    ``invalid_request`` is deliberately excluded here — it often signals a
    model-specific content-filter rejection that a different provider would
    handle successfully.
    """
    category = classify_error(exc)
    if category == "auth":
        return True
    err_msg = str(exc).lower()
    high_confidence = (
        "invalid_api_key",
        "insufficient_quota",
        "account_deactivated",
        "billing",
    )
    return any(s in err_msg for s in high_confidence)

class FallbackLLM:
    """Multilevel fallback chain for chat models.

    Wraps a primary LLM with a list of fallbacks. All chat-model surface
    methods (bind_tools, with_structured_output, invoke, stream, etc.) are
    forwarded to each member individually, so the fallback chain works with
    LangGraph agent nodes that expect a ``BaseChatModel`` interface.
    """

    def __init__(self, primary: Any, fallbacks: list[Any] | Any):
        self.primary = primary
        if isinstance(fallbacks, list):
            self.fallbacks = fallbacks
        else:
            self.fallbacks = [fallbacks]

    def __repr__(self) -> str:
        return (
            f"FallbackLLM(primary={self.primary.model_name}, "
            f"fallbacks={[getattr(fb, 'model_name', str(fb)) for fb in self.fallbacks]})"
        )

    def _combined(self):
        fallback_list = self.fallbacks.copy()
        if not fallback_list:
            logger.debug("FallbackLLM: no fallbacks configured, returning primary only")
        else:
            logger.debug(
                "FallbackLLM: chain ready — primary=%s, fallbacks=%s",
                self.primary.model_name,
                [getattr(fb, "model_name", "?") for fb in fallback_list],
            )
        return self.primary.with_fallbacks(fallback_list)

    def _fallbacks_combined(self):
        """Return a chain that starts *after* the primary model.

        ``invoke``/``ainvoke`` optimistically call the primary themselves so
        permanent failures can be classified before failover.  Retrying via
        ``_combined`` would put that same primary at the head of the chain and
        send the failed request a second time before reaching a fallback.
        """
        if not self.fallbacks:
            return None
        return self.fallbacks[0].with_fallbacks(self.fallbacks[1:])

    def bind_tools(self, tools, **kwargs):
        bound_fallbacks = []
        for fb in self.fallbacks:
            try:
                bound_fallbacks.append(fb.bind_tools(tools, **kwargs))
            except Exception as exc:
                logger.warning(
                    "FallbackLLM: failed to bind_tools on fallback %s: %s — dropping",
                    getattr(fb, "model_name", "?"),
                    exc,
                )
        return self.primary.bind_tools(tools, **kwargs).with_fallbacks(bound_fallbacks)

    def with_structured_output(self, schema, **kwargs):
        bound_fallbacks = []
        for fb in self.fallbacks:
            try:
                bound_fallbacks.append(fb.with_structured_output(schema, **kwargs))
            except Exception as exc:
                logger.warning(
                    "FallbackLLM: with_structured_output failed on fallback %s: %s — dropping",
                    getattr(fb, "model_name", "?"),
                    exc,
                )
        return self.primary.with_structured_output(schema, **kwargs).with_fallbacks(bound_fallbacks)

    def with_config(self, *args, **kwargs):
        return FallbackLLM(
            self.primary.with_config(*args, **kwargs),
            [fb.with_config(*args, **kwargs) for fb in self.fallbacks],
        )

    def invoke(self, *args, **kwargs):
        try:
            return self.primary.invoke(*args, **kwargs)
        except Exception as exc:
            if _is_permanent_failure(exc):
                raise
            fallback_chain = self._fallbacks_combined()
            if fallback_chain is None:
                raise
            return fallback_chain.invoke(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        try:
            return await self.primary.ainvoke(*args, **kwargs)
        except Exception as exc:
            if _is_permanent_failure(exc):
                raise
            fallback_chain = self._fallbacks_combined()
            if fallback_chain is None:
                raise
            return await fallback_chain.ainvoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._combined().stream(*args, **kwargs)

    def astream(self, *args, **kwargs):
        return self._combined().astream(*args, **kwargs)

    def astream_events(self, *args, **kwargs):
        """Passthrough to primary's ``astream_events``.

        LangGraph uses ``astream_events`` for streaming event-based output.
        This forwards ``with_fallbacks``-wrapped runnable's events.
        """
        return self._combined().astream_events(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.primary, name)
