"""The auditor must judge the debate against everything the debaters saw.

The bull/bear researchers receive the Synthesis Report and the Analyst
Cross-Examination Q&A next to the analyst reports, and their prompts instruct
them to cite both.  When the auditor's ground truth held only analyst reports,
those legitimate citations were reported as fabricated sources and the Final
Auditor Note directed the Research Manager to discard grounded arguments.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _CapturingLLM:
    def __init__(self) -> None:
        self.prompt = ""

    async def ainvoke(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(content="Audit Executive Summary: Pass")


def _state(**overrides):
    state = {
        "company_of_interest": "MSFT",
        "asset_type": "stock",
        "market_report": "Market report body",
        "investment_debate_state": {"history": "Bull Analyst: cites the Synthesis Report."},
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_auditor_ground_truth_includes_synthesis_and_cross_examination(monkeypatch):
    from backend.trading_agents.agents.sub.managers import auditor_node as auditor_module

    monkeypatch.setattr(
        auditor_module,
        "get_general_settings_block",
        lambda: "",
    )

    llm = _CapturingLLM()
    node = auditor_module.create_auditor_node(llm)

    result = await node(
        _state(
            synthesis_report="Critical Conflicts: valuation vs momentum.",
            agent_qa_report="Q -> Valuation Analyst: explain the P/B premium.",
        )
    )

    ground_truth = llm.prompt.split("### Investment Debate Transcript:")[0]
    assert "Market report body" in ground_truth
    assert "Critical Conflicts: valuation vs momentum." in ground_truth
    assert "Q -> Valuation Analyst: explain the P/B premium." in ground_truth
    assert result["audit_report"].startswith("Audit Executive Summary")


@pytest.mark.asyncio
async def test_auditor_omits_documents_that_were_never_produced(monkeypatch):
    """A disabled/failed synthesis must not become an empty citable heading."""
    from backend.trading_agents.agents.sub.managers import auditor_node as auditor_module

    monkeypatch.setattr(auditor_module, "get_general_settings_block", lambda: "")

    llm = _CapturingLLM()
    node = auditor_module.create_auditor_node(llm)

    await node(_state(synthesis_report="", agent_qa_report=None))

    ground_truth = llm.prompt.split("### Investment Debate Transcript:")[0]
    assert "Market report body" in ground_truth
    assert "Synthesis Report" not in ground_truth
    assert "Analyst Cross-Examination" not in ground_truth
