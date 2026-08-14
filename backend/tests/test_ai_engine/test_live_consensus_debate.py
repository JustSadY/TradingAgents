from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.analysis.emitter import AnalysisEmitter
from backend.trading_agents.agents.data.chart_tools import active_run_context
from backend.trading_agents.agents.runtime.debate_stream import emit_live_debate_state


class _Tracker:
    def __init__(self) -> None:
        self.touches = 0

    def touch(self) -> None:
        self.touches += 1


class _FakeEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit_debate_bubble(
        self,
        debate_type: str,
        message: str,
        *,
        sender: str | None = None,
        content: str | None = None,
        expect_graph_replay: bool = False,
    ) -> None:
        self.events.append(
            {
                "debate_type": debate_type,
                "message": message,
                "sender": sender,
                "content": content,
                "expect_graph_replay": expect_graph_replay,
            }
        )


@pytest.mark.asyncio
async def test_live_debate_bridge_emits_only_new_turns() -> None:
    emitter = _FakeEmitter()
    tracker = _Tracker()
    token = active_run_context.set({"emitter": emitter, "activity_tracker": tracker})
    try:
        assert await emit_live_debate_state(
            "investment",
            {
                "count": 1,
                "history": "Bull Analyst: First bullish argument.",
            },
        ) == 1
        assert await emit_live_debate_state(
            "investment",
            {
                "count": 2,
                "history": "Bull Analyst: First bullish argument.\nBear Analyst: First bearish response.",
            },
        ) == 1
        # The enclosing LangGraph node may expose the same final state again;
        # the inner-loop bridge itself must not republish an already-seen count.
        assert await emit_live_debate_state(
            "investment",
            {
                "count": 2,
                "history": "Bull Analyst: First bullish argument.\nBear Analyst: First bearish response.",
            },
        ) == 0
    finally:
        active_run_context.reset(token)

    assert [event["sender"] for event in emitter.events] == ["Bull Analyst", "Bear Analyst"]
    assert all(event["expect_graph_replay"] is True for event in emitter.events)
    assert tracker.touches == 2


@pytest.mark.asyncio
async def test_emitter_suppresses_exactly_one_graph_replay_per_live_turn(monkeypatch) -> None:
    emitter = AnalysisEmitter("debate-test")
    sent: list[dict] = []

    async def capture(event: dict) -> None:
        sent.append(event)

    monkeypatch.setattr(emitter, "emit", capture)

    kwargs = {
        "debate_type": "investment",
        "message": "Bull Analyst: Same text.",
        "sender": "Bull Analyst",
        "content": "Same text.",
    }
    await emitter.emit_debate_bubble(**kwargs, expect_graph_replay=True)
    await emitter.emit_debate_bubble(**kwargs)  # graph observer replay: suppressed
    assert len(sent) == 1

    # A genuinely later turn with identical model text must still be emitted;
    # only its own later observer replay is consumed.
    await emitter.emit_debate_bubble(**kwargs, expect_graph_replay=True)
    await emitter.emit_debate_bubble(**kwargs)
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_research_consensus_streams_each_turn_and_fallback_preserves_alternation(monkeypatch) -> None:
    from backend.trading_agents.agents.main import research as research_module

    calls: list[str] = []

    async def failing_bull(_state):
        calls.append("bull")
        raise RuntimeError("provider unavailable")

    async def working_bear(state):
        calls.append("bear")
        debate = state["investment_debate_state"]
        argument = "Bear Analyst: Bear turn still runs after the Bull fallback."
        history = str(debate.get("history", "") or "").strip()
        return {
            "investment_debate_state": {
                "history": f"{history}\n{argument}".strip(),
                "bull_history": str(debate.get("bull_history", "") or ""),
                "bear_history": argument,
                "current_response": argument,
                "judge_decision": "",
                "count": int(debate.get("count", 0) or 0) + 1,
            }
        }

    async def judge(_state):
        return {"investment_plan": "Consensus complete."}

    monkeypatch.setattr(research_module, "create_bull_researcher", lambda _llm: failing_bull)
    monkeypatch.setattr(research_module, "create_bear_researcher", lambda _llm: working_bear)
    monkeypatch.setattr(research_module, "create_research_manager", lambda _llm: judge)

    class _Ctx:
        # String input intentionally covers settings/config deserialisation.
        config = {"max_debate_rounds": "1"}

        @staticmethod
        def is_enabled(key: str) -> bool:
            return key in {"research_manager", "bull_researcher", "bear_researcher"}

        @staticmethod
        def llm_for(_key: str):
            return SimpleNamespace()

    emitter = _FakeEmitter()
    token = active_run_context.set({"emitter": emitter, "activity_tracker": _Tracker()})
    try:
        result = await research_module.create_research_manager_node(_Ctx())({})
    finally:
        active_run_context.reset(token)

    assert calls == ["bull", "bear"]
    debate = result["investment_debate_state"]
    assert debate["count"] == 2
    assert "Bull Analyst: This debate turn was unavailable" in debate["history"]
    assert "Bear Analyst: Bear turn still runs" in debate["history"]
    assert [event["sender"] for event in emitter.events] == ["Bull Analyst", "Bear Analyst"]
    assert result["investment_plan"] == "Consensus complete."
