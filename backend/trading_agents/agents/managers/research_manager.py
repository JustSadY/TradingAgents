from __future__ import annotations
from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        investment_debate_state = state["investment_debate_state"]
        audit_report = state.get("audit_report", "No audit report available.")
        
        from tradingagents.dataflows.config import get_config
        strict_learning = get_config().get("strict_backtest_learning", True)
        learning_instruction = ""
        if strict_learning:
            learning_instruction = (
                "- **STRICT LEARNING:** You MUST explicitly weight the 'Historical Baseline' (backtests) provided in the Synthesis report.\n"
                "- If historical win rates are below 50%, you MUST provide a high-caution justification if you recommend a Buy.\n"
            )

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.
{instrument_context}
---
**Audit Report (Fact-Check):**
{audit_report}
---
**Instructional Constraints:**
{learning_instruction}
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
        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )
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
