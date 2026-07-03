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

from typing import Any


class FallbackLLM:
    def __init__(self, primary: Any, fallbacks: list[Any] | Any):
        self.primary = primary
        if isinstance(fallbacks, list):
            self.fallbacks = fallbacks
        else:
            self.fallbacks = [fallbacks]

    def _combined(self):
        return self.primary.with_fallbacks(self.fallbacks)

    def bind_tools(self, tools, **kwargs):
        return self.primary.bind_tools(tools, **kwargs).with_fallbacks(
            [fb.bind_tools(tools, **kwargs) for fb in self.fallbacks]
        )

    def with_structured_output(self, schema, **kwargs):
        return self.primary.with_structured_output(schema, **kwargs).with_fallbacks(
            [fb.with_structured_output(schema, **kwargs) for fb in self.fallbacks]
        )

    def with_config(self, *args, **kwargs):
        return FallbackLLM(
            self.primary.with_config(*args, **kwargs),
            [fb.with_config(*args, **kwargs) for fb in self.fallbacks],
        )

    def invoke(self, *args, **kwargs):
        return self._combined().invoke(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        return await self._combined().ainvoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._combined().stream(*args, **kwargs)

    def astream(self, *args, **kwargs):
        return self._combined().astream(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.primary, name)
