from backend.trading_agents.agents.runtime.report_aggregator import build_resources
from backend.trading_agents.agents.utils.agent_utils import get_language_instruction


def create_conservative_debator(llm):
    async def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")
        trader_decision = state["trader_investment_plan"]

        report_fields = {
            "market_report": "Market Research Report",
            "sentiment_report": "Social Media Sentiment Report",
            "news_report": "Latest World Affairs Report",
            "fundamentals_report": "Company Fundamentals Report",
            "macro_report": "Macroeconomic Indicators Report",
            "options_report": "Options Market Derivatives Report",
            "quant_report": "Quantitative Metrics Report",
            "earnings_report": "Corporate Guidance & Earnings Report",
            "review_report": "Hindsight Performance Review Report",
        }
        resources_text = build_resources(state, report_fields)

        prompt = f"""As the Conservative Risk Analyst, your role is to prioritize capital preservation and emphasize high-probability, low-risk outcomes. When evaluating the trader's decision or plan, look specifically for potential downsides, hidden risks, and worst-case scenarios. Challenge the arguments of the aggressive and neutral analysts by highlighting where their optimism may lead to significant losses. Use the provided market data and sentiment insights to justify a more cautious approach. Respond directly to the points raised by your counterparts, identifying logical flaws and risks they have overlooked. Here is the trader's decision:
{trader_decision}
Your goal is to offer a rigorous critique of the proposed decision from a standpoint of extreme prudence. Question the aggressive and neutral viewpoints by showing how a more conservative stance better protects the portfolio. Use insights from these sources:
{resources_text}
Here is the current conversation history: {history} Here are the last arguments from the aggressive analyst: {current_aggressive_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other analysts yet, begin with your own analysis.
Maintain a focus on questioning assumptions, identifying threats, and persuading the team toward a lower-risk path. Avoid merely presenting data—be critical and defensive in your approach. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        response = await llm.ainvoke(prompt)
        argument = f"Conservative Analyst: {response.content}"
        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "conservative_history": conservative_history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_conservative_response": argument,
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }
        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
