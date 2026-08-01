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

class _SequenceLLM:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        self.calls += 1
        return self._responses.pop(0)

def test_analyst_cache_rejects_blank_reports() -> None:
    from backend.trading_agents.agents.runtime.analyst_cache import _usable_report

    assert _usable_report(" \n\t") is None
    assert _usable_report(None) is None
    assert _usable_report("  usable report  ") == "usable report"

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
async def test_tool_analyst_recovers_an_empty_final_report(monkeypatch):
    """A blank provider response must not become a blank persisted report."""
    from backend.trading_agents.agents.runtime import analyst_node_factory, resilience

    async def call_once(fn, **_kwargs):
        return await fn()

    monkeypatch.setattr(analyst_node_factory, "ChatPromptTemplate", _Prompt)
    monkeypatch.setattr(analyst_node_factory, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(resilience, "retry_call", call_once)

    llm = _SequenceLLM(
        SimpleNamespace(content=" \n\t", tool_calls=[]),
        SimpleNamespace(content="Recovered market report", tool_calls=[]),
    )
    result = await analyst_node_factory.run_tool_analyst(
        llm,
        {"company_of_interest": "AAPL", "trade_date": "2026-08-01", "messages": []},
        tools=[],
        system_message="test instructions",
        report_key="market_report",
        instrument_context="test context",
    )

    assert result["market_report"] == "Recovered market report"
    assert llm.calls == 2

@pytest.mark.asyncio
async def test_tool_analyst_exposes_a_visible_degraded_report_when_recovery_is_empty(monkeypatch):
    from backend.trading_agents.agents.runtime import analyst_node_factory, resilience

    async def call_once(fn, **_kwargs):
        return await fn()

    monkeypatch.setattr(analyst_node_factory, "ChatPromptTemplate", _Prompt)
    monkeypatch.setattr(analyst_node_factory, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(resilience, "retry_call", call_once)

    result = await analyst_node_factory.run_tool_analyst(
        _SequenceLLM(
            SimpleNamespace(content="", tool_calls=[]),
            SimpleNamespace(content=" ", tool_calls=[]),
        ),
        {"company_of_interest": "AAPL", "trade_date": "2026-08-01", "messages": []},
        tools=[],
        system_message="test instructions",
        report_key="market_report",
        instrument_context="test context",
    )

    assert result["market_report"].startswith("⚠️ Market analysis unavailable:")

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
    start = next(fields for event, fields in events if event == "node_start")
    assert start["phase"] == "initial"
    assert start["turn"] == 1

@pytest.mark.asyncio
async def test_guard_node_marks_post_tool_analyst_invocations_as_continuations(monkeypatch):
    """ToolNode loops are real LLM turns, but must not look like duplicate starts."""
    from backend.trading_agents.agents.runtime import resilience

    events = []

    def capture(event, **fields):
        events.append((event, fields))

    async def call_once(fn, **_kwargs):
        return await fn()

    async def analyst_node(_state):
        return {"market_report": "final report"}

    assistant_tool_request = SimpleNamespace(type="ai", tool_calls=[{"name": "get_stock_data"}])
    tool_result_one = SimpleNamespace(type="tool")
    tool_result_two = SimpleNamespace(type="tool")
    state = {
        "messages": [
            SimpleNamespace(type="human"),
            assistant_tool_request,
            tool_result_one,
            tool_result_two,
        ]
    }

    monkeypatch.setattr(resilience, "log_event", capture)
    monkeypatch.setattr(resilience, "retry_call", call_once)
    resilience._circuit_state.clear()

    result = await resilience.guard_node(
        analyst_node,
        name="Market Analyst",
        kind="analyst",
    )(state)

    assert result == {"market_report": "final report"}
    starts = [fields for event, fields in events if event == "node_start"]
    ends = [fields for event, fields in events if event == "node_end"]
    assert starts == [
        {
            "node": "Market Analyst",
            "kind": "analyst",
            "phase": "continuation",
            "turn": 2,
            "tool_results": 2,
        }
    ]
    assert ends[0]["phase"] == "continuation"
    assert ends[0]["turn"] == 2
    assert ends[0]["tool_results"] == 2
