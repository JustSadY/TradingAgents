"""Regressions for analysis liveness and coordinator retry boundaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.services.analysis.activity import AnalysisActivityTracker, touch_current_analysis
from backend.services.analysis.orchestrator import _heartbeat_monitor
from backend.services.analysis.streaming_handler import TokenStreamingCallbackHandler
from backend.trading_agents.agents.data.chart_tools import active_run_context
from backend.trading_agents.agents.runtime import resilience


class _Emitter:
    task_id = "liveness-test"

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.progress: list[tuple[str, str, str]] = []

    async def emit(self, event: dict) -> None:
        self.events.append(event)

    async def emit_progress(self, label: str, stage: str, node: str) -> None:
        self.progress.append((label, stage, node))


@pytest.mark.asyncio
async def test_streaming_callback_refreshes_only_its_task_activity_tracker():
    now = [0.0]
    tracker = AnalysisActivityTracker(clock=lambda: now[0])
    handler = TokenStreamingCallbackHandler(_Emitter(), activity_tracker=tracker)

    now[0] = 41.0
    await handler.on_llm_start({}, ["prompt"], run_id=uuid4())

    assert tracker.last_activity_at() == 41.0


@pytest.mark.asyncio
async def test_heartbeat_stays_running_when_callback_activity_arrives():
    now = [0.0]
    tracker = AnalysisActivityTracker(clock=lambda: now[0])
    emitter = _Emitter()
    sleep_calls = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        now[0] += seconds
        # This models a provider token/tool callback while the graph has not
        # yielded a state update yet.
        tracker.touch()
        if sleep_calls > 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _heartbeat_monitor(
            emitter,
            tracker.last_activity_at,
            stall_timeout=10,
            sleep=fake_sleep,
            now=lambda: now[0],
        )

    assert not [event for event in emitter.events if event["type"] == "stall_warning"]
    assert emitter.progress == [
        ("heartbeat", "running", "system"),
        ("heartbeat", "running", "system"),
    ]


def test_touch_current_analysis_uses_the_current_task_tracker():
    now = [0.0]
    tracker = AnalysisActivityTracker(clock=lambda: now[0])
    token = active_run_context.set({"activity_tracker": tracker})
    try:
        now[0] = 7.0
        touch_current_analysis()
    finally:
        active_run_context.reset(token)

    assert tracker.last_activity_at() == 7.0


@pytest.mark.asyncio
async def test_retry_call_retries_an_empty_asyncio_timeout_as_transient():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return "recovered"

    assert (
        await resilience.retry_call(
            flaky,
            label="test-timeout",
            attempts=2,
            base_delay=0,
            timeout=1,
        )
        == "recovered"
    )
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_call_does_not_repeat_a_degraded_provider_function():
    calls = 0

    async def unavailable():
        nonlocal calls
        calls += 1
        raise RuntimeError("Function id 'abc': DEGRADED function cannot be invoked")

    with pytest.raises(RuntimeError, match="DEGRADED"):
        await resilience.retry_call(
            unavailable,
            label="test-degraded",
            attempts=2,
            base_delay=0,
            timeout=1,
        )

    assert calls == 1


@pytest.mark.asyncio
async def test_guard_node_forwards_composite_timeout_and_no_timeout_retry(monkeypatch):
    captured: dict = {}

    async def fake_retry(fn, **kwargs):
        captured.update(kwargs)
        return await fn()

    async def node(_state):
        return {"ok": True}

    monkeypatch.setattr(resilience, "retry_call", fake_retry)
    tracker = AnalysisActivityTracker()
    token = active_run_context.set(
        {
            "activity_tracker": tracker,
            "graph": SimpleNamespace(config={"node_timeout_seconds": 120}),
        }
    )
    try:
        result = await resilience.guard_node(
            node,
            name="Research Manager",
            kind="main",
            timeout_multiplier=5,
            retry_timeouts=False,
        )({})
    finally:
        active_run_context.reset(token)

    assert result == {"ok": True}
    assert captured["timeout_multiplier"] == 5
    assert captured["retry_timeouts"] is False
    assert captured["retry_all"] is False
    assert captured["runtime_config"] == {"node_timeout_seconds": 120}


def test_graph_setup_uses_composite_timeouts_without_signature_regression(monkeypatch):
    """Building the graph must pass coordinator timeout policy to guard_node."""
    from backend.trading_agents.graph import setup as graph_setup

    captured: dict[str, dict] = {}
    real_guard = graph_setup.guard_node

    def tracking_guard(fn, **kwargs):
        captured[kwargs["name"]] = kwargs
        return real_guard(fn, **kwargs)

    async def empty_node(_state):
        return {}

    monkeypatch.setattr(graph_setup, "sync_registry_to_graph", lambda: None)
    monkeypatch.setattr(graph_setup, "guard_node", tracking_guard)
    monkeypatch.setattr(graph_setup, "create_market_intelligence_node", lambda _ctx: empty_node)
    monkeypatch.setattr(graph_setup, "create_agent_qa_node", lambda _ctx: empty_node)
    monkeypatch.setattr(graph_setup, "create_research_manager_node", lambda _ctx: empty_node)
    monkeypatch.setattr(graph_setup, "create_risk_debate_node", lambda _ctx: empty_node)
    monkeypatch.setattr(graph_setup, "create_portfolio_manager_node", lambda _ctx: empty_node)

    setup = graph_setup.GraphSetup(
        llm=object(),
        tool_nodes={},
        conditional_logic=object(),
        analyst_concurrency_limit=1,
        config={"max_debate_rounds": 1},
    )
    setup.setup_graph(["market", "fundamentals"])

    assert captured["Market Intelligence"]["timeout_multiplier"] == 2
    assert captured["Research Manager"]["timeout_multiplier"] == 5
    assert captured["Research Manager"]["retry_timeouts"] is False
    assert "Trader" not in captured
