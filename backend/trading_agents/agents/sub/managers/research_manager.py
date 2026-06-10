from __future__ import annotations

from backend.trading_agents.agents.runtime.report_aggregator import tail_history
from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import ResearchPlan, render_research_plan
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    async def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = tail_history(state["investment_debate_state"].get("history", ""))
        investment_debate_state = state["investment_debate_state"]
        audit_report = state.get("audit_report", "No audit report available.")
        agent_qa_report = state.get("agent_qa_report") or "No cross-examination available."

        from backend.trading_agents.dataflows.config import get_config

        # Recall the most similar past situations from episodic memory so the plan
        # can avoid repeating an action that previously led to a loss.
        memory_lessons = ""
        try:
            from backend.services.memory_service import recall_episode_lessons

            situation = state.get("market_report") or state.get("synthesis_report") or ""
            memory_lessons = await recall_episode_lessons(
                user_id=get_config().get("user_id"), situation_text=situation
            )
        except Exception:  # noqa: BLE001 — memory is best-effort
            memory_lessons = ""

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.
{instrument_context}
---
**Audit Report (Fact-Check):**
{audit_report}
---
**Analyst Cross-Examination (how the analysts reconciled their conflicts):**
{agent_qa_report}
---
{memory_lessons}
---
**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position
Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.
---
**Debate History:**
{history}""" + get_language_instruction()

        result = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            "Research Manager",
            schema=ResearchPlan,
        )

        if isinstance(result, str):
            investment_plan = result
        else:
            investment_plan = render_research_plan(result)

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }
        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
