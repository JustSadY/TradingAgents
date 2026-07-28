from types import SimpleNamespace

import pytest


class _Prompt:
    @classmethod
    def from_messages(cls, _messages):
        return cls()

    def partial(self, **_kwargs):
        return self

    def __or__(self, llm):
        return llm


class _LLM:
    def __init__(self, response):
        self._response = response

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        return self._response


@pytest.mark.asyncio
async def test_tool_analyst_leaves_lifecycle_logging_to_guard_node(monkeypatch):
    """A single graph-node turn must not emit a second key-based lifecycle."""
    from backend.trading_agents.agents.runtime import analyst_node_factory, resilience

    events = []

    def capture(event, **fields):
        events.append((event, fields))

    async def call_once(fn, **_kwargs):
        return await fn()

    monkeypatch.setattr(analyst_node_factory, "ChatPromptTemplate", _Prompt)
    monkeypatch.setattr(analyst_node_factory, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(resilience, "log_event", capture)
    monkeypatch.setattr(resilience, "retry_call", call_once)

    response = SimpleNamespace(content="Fundamentals report", tool_calls=[])
    result = await analyst_node_factory.run_tool_analyst(
        _LLM(response),
        {"company_of_interest": "AAPL", "trade_date": "2026-07-28", "messages": []},
        tools=[],
        system_message="test instructions",
        report_key="fundamentals_report",
        instrument_context="test context",
    )

    assert result["fundamentals_report"] == "Fundamentals report"
    assert not [event for event, _fields in events if event in {"node_start", "node_end"}]


@pytest.mark.asyncio
async def test_guard_node_remains_the_single_analyst_lifecycle_source(monkeypatch):
    from backend.trading_agents.agents.runtime import resilience

    events = []

    def capture(event, **fields):
        events.append((event, fields))

    async def call_once(fn, **_kwargs):
        return await fn()

    async def analyst_node(_state):
        return {"fundamentals_report": "ok"}

    monkeypatch.setattr(resilience, "log_event", capture)
    monkeypatch.setattr(resilience, "retry_call", call_once)
    resilience._circuit_state.clear()

    result = await resilience.guard_node(
        analyst_node,
        name="Fundamentals Analyst",
        kind="analyst",
    )({})

    assert result == {"fundamentals_report": "ok"}
    assert [(event, fields["node"]) for event, fields in events] == [
        ("node_start", "Fundamentals Analyst"),
        ("node_end", "Fundamentals Analyst"),
    ]
