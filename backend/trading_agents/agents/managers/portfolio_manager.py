from __future__ import annotations
import json
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision, TraderProposal
from tradingagents.agents.utils.risk_math import calculate_kelly_size, get_risk_reward_from_plan
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")
    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        trader_proposal_json = state.get("trader_proposal_json")

        from tradingagents.dataflows.config import get_config
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
                        f"- Estimated Win Probability: {tp.confidence_score*100:.1f}%\n"
                        f"- Suggested Maximum Position Size: {kelly_pct*100:.1f}% of portfolio.\n"
                        "Note: Use this as a ceiling for your final sizing decision.\n"
                    )
            except Exception:
                pass

        past_context = state.get("past_context", "")
        if past_context:
            lessons_line = f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            conviction_instructions = (
                "---\n\n"
                "**Crucial Sizing & Conviction Instructions:**\n"
                "- Carefully evaluate the \"Lessons from prior decisions and outcomes\" listed above.\n"
                "- Identify which analysts or strategies were noted as over-optimistic or prone to error in prior hindsight reviews, and dynamically discount or adjust their conviction scores in your current thesis.\n"
                "- Ground your final position sizing and entry target in these empirical learning adjustments.\n"
            )
        else:
            lessons_line = ""
            conviction_instructions = ""
        from tradingagents.dataflows.config import get_config
        persona = get_config().get("investor_persona", "conservative")
        persona_instructions = ""
        if persona == "conservative":
            persona_instructions = (
                "**INVESTOR PERSONA: Conservative Dividend Investor (Muhafazakar)**\n"
                "- Your client is highly risk-averse, focusing on capital preservation, steady income (dividends), and low-volatility blue-chip assets.\n"
                "- Prefer 'Hold' or 'Sell/Underweight' if uncertainty is high. Do not recommend aggressive positioning, high leverage, or speculative assets unless backed by overwhelming positive fundamental data.\n"
                "- Keep position sizing conservative, prioritizing cash safety.\n"
            )
        elif persona == "risk_loving":
            persona_instructions = (
                "**INVESTOR PERSONA: Risk-Loving Crypto & Growth Trader (Risk Sever)**\n"
                "- Your client seeks high returns and is willing to accept high volatility, leverage, and speculative growth or crypto assets.\n"
                "- Emphasize growth potential and momentum. Be willing to recommend 'Buy' or 'Overweight' sizing if there is a strong technical breakout or high social sentiment, even if fundamentals are weak or debate is mixed.\n"
            )
        elif persona == "esg_focused":
            persona_instructions = (
                "**INVESTOR PERSONA: Sustainability / ESG-Focused Investor (ESG Odaklı)**\n"
                "- Your client prioritizes environmental, social, and corporate governance metrics alongside financial returns.\n"
                "- Strictly penalize companies with controversial environmental track records, poor corporate governance, or regulatory issues. Heavily favor clean energy, positive social governance, and sustainable business models.\n"
            )
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
        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )
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
