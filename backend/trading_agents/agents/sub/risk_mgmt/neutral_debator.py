from backend.trading_agents.agents.sub.risk_mgmt.base import make_risk_debator


def _default_instruction() -> str:
    return (
        "As the Neutral Risk Analyst, your objective is to provide a balanced, objective evaluation that "
        "mediates between aggressive and conservative perspectives. Focus on realistic outcomes and "
        "evidence-based probabilities, neither leaning toward excessive optimism nor undue caution. When "
        "reviewing the trader's decision, weigh the potential rewards against the risks fairly. Respond to "
        "both the aggressive and conservative analysts by highlighting where their arguments are strong "
        "and where they are biased."
    )


def _build_prompt(instruction: str, trader_decision: str, resources_text: str, recent_history: str, risk_debate_state: dict) -> str:
    current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
    current_conservative_response = risk_debate_state.get("current_conservative_response", "")
    return f"""{instruction} Here is the trader's decision:
{trader_decision}
Your task is to critique and refine the trader's proposal by identifying a middle ground. Address the points from the aggressive and conservative viewpoints, using data to bring a more grounded perspective to the debate. Use insights from the following:
{resources_text}
Current conversation history: {recent_history}. Last argument from the aggressive analyst: {current_aggressive_response}. Last argument from the conservative analyst: {current_conservative_response}. If no other arguments are available, provide your baseline neutral assessment.
Focus on being an objective mediator. Highlight divergences in the other analysts' logic and suggest a balanced approach based on the available facts. Output conversationally as if you are speaking without any special formatting."""


create_neutral_debator = make_risk_debator("neutral", "Neutral", _build_prompt, _default_instruction)
