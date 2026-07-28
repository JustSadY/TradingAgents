from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode


@tool
async def _unavailable_tool(ticker: str) -> str:
    """A deterministic external-data failure for ToolNode telemetry tests."""
    raise RuntimeError("vendor timed out token=super-secret-tool-token")


@pytest.mark.asyncio
async def test_tool_failure_keeps_identity_redacts_secrets_and_returns_tool_message(monkeypatch):
    """A failed tool must be diagnosable without aborting the analyst turn."""
    from backend.trading_agents.agents.runtime import resilience
    from backend.trading_agents.agents.runtime.tool_telemetry import make_async_tool_call_wrapper, tool_error_handler

    events: list[tuple[str, dict]] = []

    def capture(event: str, **fields) -> None:
        events.append((event, fields))

    monkeypatch.setattr(resilience, "log_event", capture)
    tool_node = ToolNode(
        [_unavailable_tool],
        handle_tool_errors=tool_error_handler,
        awrap_tool_call=make_async_tool_call_wrapper("fundamentals"),
    )
    workflow = StateGraph(MessagesState)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)

    result = await workflow.compile().ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "_unavailable_tool", "args": {"ticker": "AAPL"}, "id": "call-1", "type": "tool_call"}
                    ],
                )
            ]
        }
    )

    response = result["messages"][-1]
    assert response.name == "_unavailable_tool"
    assert response.tool_call_id == "call-1"
    assert response.status == "error"
    assert "super-secret-tool-token" not in response.content
    assert "***REDACTED***" in response.content
    assert events == [
        (
            "tool_error",
            {
                "level": 30,
                "tool": "_unavailable_tool",
                "analyst": "fundamentals",
                "call_id": "call-1",
                "error_type": "timeout",
                "action": "continue_without_tool",
                "error": "vendor timed out token=***REDACTED***",
            },
        )
    ]


def test_tool_timeout_builds_one_valid_response_for_each_pending_call(monkeypatch):
    from backend.trading_agents.agents.runtime import resilience
    from backend.trading_agents.agents.runtime.tool_telemetry import log_tool_timeout

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(resilience, "log_event", lambda event, **fields: events.append((event, fields)))
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_fundamentals", "args": {}, "id": "fundamentals-1", "type": "tool_call"},
                    {"name": "get_cashflow", "args": {}, "id": "cashflow-1", "type": "tool_call"},
                ],
            )
        ]
    }

    responses = log_tool_timeout(state, analyst="fundamentals", timeout_seconds=60)

    assert [(message.name, message.tool_call_id, message.status) for message in responses] == [
        ("get_fundamentals", "fundamentals-1", "error"),
        ("get_cashflow", "cashflow-1", "error"),
    ]
    assert events[0] == (
        "tool_timeout",
        {
            "level": 30,
            "tool": None,
            "tools": ["get_fundamentals", "get_cashflow"],
            "analyst": "fundamentals",
            "error_type": "timeout",
            "action": "continue_without_tool",
            "timeout_seconds": 60.0,
            "error": "Timed out after 60s",
        },
    )
