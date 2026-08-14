from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.trading_agents.agents.runtime.resilience import get_report_card, init_report_card


@pytest.mark.asyncio
async def test_final_research_judge_failure_preserves_branch_and_marks_run_degraded(monkeypatch) -> None:
    from backend.trading_agents.agents.main import research as research_module

    async def failing_judge(_state):
        raise RuntimeError("structured response could not be validated")

    monkeypatch.setattr(research_module, "create_research_manager", lambda _llm: failing_judge)

    class _Ctx:
        config = {"max_debate_rounds": 1}

        @staticmethod
        def is_enabled(key: str) -> bool:
            # Keep this focused on the final judgement failure. The branch must
            # still return a usable degraded state instead of aborting the graph.
            return key == "research_manager"

        @staticmethod
        def llm_for(_key: str):
            return SimpleNamespace()

    init_report_card()
    result = await research_module.create_research_manager_node(_Ctx())({})

    assert "Research judgement unavailable" in result["investment_plan"]
    assert result["investment_debate_state"]["judge_decision"] == result["investment_plan"]
    assert result["investment_debate_state"]["count"] == 0

    card = get_report_card()
    assert card["research_manager"]["fallback"] is True
    assert "structured response could not be validated" in card["research_manager"]["error"]
