"""Invocation-time provider failover for chat models.

``Runnable.with_fallbacks`` cannot be applied to a chat model up front: the
resulting wrapper is not a ``BaseChatModel``, so ``bind_tools`` and
``with_structured_output`` — both required by the agent nodes — disappear.
``FallbackLLM`` keeps the chat-model surface by applying those transformations
to the primary and the fallback separately, combining the results with
``with_fallbacks`` only at the Runnable boundary.
"""

from __future__ import annotations

from typing import Any


class FallbackLLM:
    def __init__(self, primary: Any, fallback: Any):
        self.primary = primary
        self.fallback = fallback

    def _combined(self):
        return self.primary.with_fallbacks([self.fallback])

    def bind_tools(self, tools, **kwargs):
        return self.primary.bind_tools(tools, **kwargs).with_fallbacks([self.fallback.bind_tools(tools, **kwargs)])

    def with_structured_output(self, schema, **kwargs):
        return self.primary.with_structured_output(schema, **kwargs).with_fallbacks(
            [self.fallback.with_structured_output(schema, **kwargs)]
        )

    def with_config(self, *args, **kwargs):
        return FallbackLLM(self.primary.with_config(*args, **kwargs), self.fallback.with_config(*args, **kwargs))

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
