from backend.trading_agents.agents.sub.risk_mgmt.base import make_risk_debator


def _default_instruction() -> str:
    return (
        "As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk "
        "opportunities, emphasizing bold strategies and competitive advantages. When evaluating the "
        "trader's decision or plan, focus intently on the potential upside, growth potential, and "
        "innovative benefits—even when these come with elevated risk. Use the provided market data and "
        "sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, "
        "respond directly to each point made by the conservative and neutral analysts, countering with "
        "data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical "
        "opportunities or where their assumptions may be overly conservative."
    )


def _build_prompt(
    instruction: str, trader_decision: str, resources_text: str, recent_history: str, risk_debate_state: dict
) -> str:
    current_conservative_response = risk_debate_state.get("current_conservative_response", "")
    current_neutral_response = risk_debate_state.get("current_neutral_response", "")
    return f"""{instruction} Here is the trader's decision:
{trader_decision}
Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:
{resources_text}
Here is the current conversation history: {recent_history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.
Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting."""


create_aggressive_debator = make_risk_debator("aggressive", "Aggressive", _build_prompt, _default_instruction)
