from backend.trading_agents.agents.runtime.report_aggregator import (
    build_report_fields,
    build_resources,
    tail_history,
)
from backend.trading_agents.agents.utils.agent_utils import get_language_instruction


def create_neutral_debator(llm):
    async def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")
        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        trader_decision = state["trader_investment_plan"]

        report_fields = build_report_fields("Latest World Affairs Report", "Company Fundamentals Report")
        # Risk debators argue over the trade decision, not the raw data, so send
        # each analyst's Executive Summary instead of the full report.
        resources_text = build_resources(state, report_fields, summary_only=True)

        prompt = f"""As the Neutral Risk Analyst, your objective is to provide a balanced, objective evaluation that mediates between aggressive and conservative perspectives. Focus on realistic outcomes and evidence-based probabilities, neither leaning toward excessive optimism nor undue caution. When reviewing the trader's decision, weigh the potential rewards against the risks fairly. Respond to both the aggressive and conservative analysts by highlighting where their arguments are strong and where they are biased. Here is the trader's decision:
{trader_decision}
Your task is to critique and refine the trader's proposal by identifying a middle ground. Address the points from the aggressive and conservative viewpoints, using data to bring a more grounded perspective to the debate. Use insights from the following:
{resources_text}
Current conversation history: {tail_history(history)}. Last argument from the aggressive analyst: {current_aggressive_response}. Last argument from the conservative analyst: {current_conservative_response}. If no other arguments are available, provide your baseline neutral assessment.
Focus on being an objective mediator. Highlight divergences in the other analysts' logic and suggest a balanced approach based on the available facts. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        response = await llm.ainvoke(prompt)
        argument = f"Neutral Analyst: {response.content}"
        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "neutral_history": neutral_history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "latest_speaker": "Neutral",
            "current_neutral_response": argument,
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "count": risk_debate_state["count"] + 1,
        }
        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
