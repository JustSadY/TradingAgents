"""
Self-contained tool-calling loop for sub-agents.

In the old flat graph each analyst was three nodes (agent → ToolNode → agent)
wired with conditional edges. In the 3-tier model a sub-agent runs *inside* its
main-agent node, so it carries its own loop instead:

    bind tools → invoke → if tool_calls: execute, append ToolMessages, repeat
                         → else: done, return the final content.

This is a drop-in replacement for the LangGraph ToolNode dance and is what a
pure Tier-2 ``SubAgent`` uses. (The analyst branch currently still reuses the
proven LangGraph sub-wiring via a compiled subgraph; this loop is the path for
new sub-agents and for callers that want a node-free executor.)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)


def run_tool_loop(
    llm: Any,
    tools: list[Any],
    messages: list[Any],
    *,
    max_iters: int = 8,
    label: str = "sub_agent",
) -> AIMessage:
    """
    Drive *llm* with *tools* until it stops requesting tool calls.

    Returns the final assistant message (the one with no pending tool calls).
    Tool execution errors are fed back to the model as ToolMessages so it can
    recover, rather than aborting the run.
    """
    if not tools:
        return llm.invoke(messages)

    bound = llm.bind_tools(tools)
    tools_by_name = {(t.name if hasattr(t, "name") else getattr(t, "__name__", str(t))): t for t in tools}

    convo = list(messages)
    last: Any = None
    for i in range(max_iters):
        last = bound.invoke(convo)
        convo.append(last)

        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return last

        for call in tool_calls:
            name = call.get("name")
            call_id = call.get("id")
            args = call.get("args", {}) or {}
            tool = tools_by_name.get(name)
            if tool is None:
                convo.append(
                    ToolMessage(
                        content=f"Tool '{name}' is not available to this agent.",
                        tool_call_id=call_id,
                    )
                )
                continue
            try:
                result = tool.invoke(args) if hasattr(tool, "invoke") else tool(**args)
                convo.append(ToolMessage(content=str(result), tool_call_id=call_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] tool '%s' failed: %s", label, name, exc)
                convo.append(
                    ToolMessage(
                        content=f"Tool '{name}' failed: {exc}",
                        tool_call_id=call_id,
                    )
                )

    logger.warning("[%s] tool loop hit max_iters=%d; returning last message.", label, max_iters)
    return last if last is not None else AIMessage(content="")


async def arun_tool_loop(
    llm: Any,
    tools: list[Any],
    messages: list[Any],
    *,
    max_iters: int = 8,
    label: str = "sub_agent",
) -> AIMessage:
    """
    Async version of run_tool_loop.
    """
    if not tools:
        return await llm.ainvoke(messages)

    bound = llm.bind_tools(tools)
    tools_by_name = {(t.name if hasattr(t, "name") else getattr(t, "__name__", str(t))): t for t in tools}

    convo = list(messages)
    last: Any = None
    for i in range(max_iters):
        last = await bound.ainvoke(convo)
        convo.append(last)

        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return last

        for call in tool_calls:
            name = call.get("name")
            call_id = call.get("id")
            args = call.get("args", {}) or {}
            tool = tools_by_name.get(name)
            if tool is None:
                convo.append(
                    ToolMessage(
                        content=f"Tool '{name}' is not available to this agent.",
                        tool_call_id=call_id,
                    )
                )
                continue
            try:
                if inspect.iscoroutinefunction(tool) or (
                    hasattr(tool, "ainvoke") and inspect.iscoroutinefunction(tool.ainvoke)
                ):
                    # Most LangChain tools have an async path
                    if hasattr(tool, "ainvoke"):
                        result = await tool.ainvoke(args)
                    else:
                        result = await tool(**args)
                else:
                    # Run sync tool in thread
                    result = await asyncio.to_thread(tool.invoke if hasattr(tool, "invoke") else tool, **args)

                convo.append(ToolMessage(content=str(result), tool_call_id=call_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] tool '%s' failed: %s", label, name, exc)
                convo.append(
                    ToolMessage(
                        content=f"Tool '{name}' failed: {exc}",
                        tool_call_id=call_id,
                    )
                )

    logger.warning("[%s] tool loop hit max_iters=%d; returning last message.", label, max_iters)
    return last if last is not None else AIMessage(content="")
