from backend.trading_agents.agents.sub.risk_mgmt.base import make_risk_debator


def _default_instruction() -> str:
    return (
        "As the Conservative Risk Analyst, your role is to prioritize capital preservation and emphasize "
        "high-probability, low-risk outcomes. When evaluating the trader's decision or plan, look "
        "specifically for potential downsides, hidden risks, and worst-case scenarios. Challenge the "
        "arguments of the aggressive and neutral analysts by highlighting where their optimism may lead "
        "to significant losses. Use the provided market data and sentiment insights to justify a more "
        "cautious approach. Respond directly to the points raised by your counterparts, identifying "
        "logical flaws and risks they have overlooked."
    )


def _build_prompt(
    instruction: str, trader_decision: str, resources_text: str, recent_history: str, risk_debate_state: dict
) -> str:
    current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
    current_neutral_response = risk_debate_state.get("current_neutral_response", "")
    return f"""{instruction} Here is the trader's decision:
{trader_decision}
Your goal is to offer a rigorous critique of the proposed decision from a standpoint of extreme prudence. Question the aggressive and neutral viewpoints by showing how a more conservative stance better protects the portfolio. Use insights from these sources:
{resources_text}
Here is the current conversation history: {recent_history} Here are the last arguments from the aggressive analyst: {current_aggressive_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other analysts yet, begin with your own analysis.
Maintain a focus on questioning assumptions, identifying threats, and persuading the team toward a lower-risk path. Avoid merely presenting data—be critical and defensive in your approach. Output conversationally as if you are speaking without any special formatting."""


create_conservative_debator = make_risk_debator("conservative", "Conservative", _build_prompt, _default_instruction)
