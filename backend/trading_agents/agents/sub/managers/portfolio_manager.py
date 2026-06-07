from __future__ import annotations

import json

from backend.trading_agents.agents.runtime.risk_math import calculate_kelly_size, get_risk_reward_from_plan
from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import PortfolioDecision, TraderProposal, render_pm_decision
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    async def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        trader_proposal_json = state.get("trader_proposal_json")

        from backend.trading_agents.dataflows.config import get_config

        kelly_enabled = get_config().get("kelly_sizing_enabled", True)

        kelly_recommendation = ""
        if trader_proposal_json and kelly_enabled:
            try:
                tp_dict = json.loads(trader_proposal_json)
                tp = TraderProposal(**tp_dict)
                if tp.entry_price and tp.stop_loss and tp.take_profit_price:
                    rr = get_risk_reward_from_plan(tp.take_profit_price, tp.stop_loss, tp.entry_price)
                    kelly_pct = calculate_kelly_size(tp.confidence_score, rr)
                    kelly_recommendation = (
                        f"\n**Mathematical Risk Recommendation (Kelly Criterion):**\n"
                        f"- Calculated R/R Ratio: {rr:.2f}\n"
                        f"- Estimated Win Probability: {tp.confidence_score * 100:.1f}%\n"
                        f"- Suggested Maximum Position Size: {kelly_pct * 100:.1f}% of portfolio.\n"
                        "Note: Use this as a ceiling for your final sizing decision.\n"
                    )
            except Exception:
                pass

        # Episodic memory: recall the most similar past situations (losses first)
        # so the final sizing/decision can avoid repeating a losing action.
        memory_lessons = ""
        try:
            from backend.services.memory_service import recall_episode_lessons

            memory_lessons = await recall_episode_lessons(
                user_id=get_config().get("user_id"),
                situation_text=state.get("market_report") or research_plan or "",
            )
        except Exception:  # noqa: BLE001 — memory is best-effort
            memory_lessons = ""

        # past_context now carries attribution / market-pulse / scenario context
        # (the old SQL recency memory has been replaced by the vector recall above).
        past_context = "\n\n".join(p for p in (memory_lessons, state.get("past_context", "")) if p)
        if past_context:
            lessons_line = f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            conviction_instructions = (
                "---\n\n"
                "**Crucial Sizing & Conviction Instructions:**\n"
                '- Carefully evaluate the "Lessons from prior decisions and outcomes" listed above.\n'
                "- Identify which analysts or strategies were noted as over-optimistic or prone to error in prior hindsight reviews, and dynamically discount or adjust their conviction scores in your current thesis.\n"
                "- Ground your final position sizing and entry target in these empirical learning adjustments.\n"
            )
        else:
            lessons_line = ""
            conviction_instructions = ""

        from backend.trading_agents.personas import DEFAULT_PERSONA, get_persona_instructions

        persona = get_config().get("investor_persona", DEFAULT_PERSONA)
        persona_instructions = get_persona_instructions(persona)

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.
{persona_instructions}
{instrument_context}
---
**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry
**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{kelly_recommendation}
{lessons_line}
**Risk Analysts Debate History:**
{history}
{conviction_instructions}---
Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        result = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            "Portfolio Manager",
        )

        if isinstance(result, str):
            final_trade_decision = result
        else:
            final_trade_decision = render_pm_decision(result)

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }
        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
