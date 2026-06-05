from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_options_data,
    get_language_instruction,
)
from backend.trading_agents.dataflows.config import get_config
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst


@register_analyst(
    key="options",
    agent_node="Options Analyst",
    clear_node="Msg Clear Options",
    tool_node="tools_options",
    report_key="options_report",
    tools=[get_options_data],
)
def create_options_analyst(llm):

    def options_analyst_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_options_data,
        ]

        system_message = (
            """You are a senior options and derivatives analyst. Your goal is to decode market expectations and institutional positioning through options chain analysis.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_options_data` to fetch latest options chain, including Put/Call ratios, Implied Volatility (IV), and Open Interest.
2. **Sentiment Assessment:** Analyze the Put/Call ratio (P/C > 1 is typically bearish/hedging; P/C < 0.7 is typically bullish).
3. **Volatility Interpretation:** Compare IV to historical levels to assess expected price movement magnitude.
4. **Positioning Synthesis:** Formulate what the "smart money" is pricing in via the derivatives market.

### Guidelines:
- High Put/Call ratios can indicate bearishness or heavy hedging.
- High Implied Volatility (IV) suggests the market expects significant price swings (e.g., around earnings).
- Look for imbalances in Open Interest between calls and puts.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical options-derived sentiment and volatility signals.
2. **Detailed Analysis:** Nuanced interpretation of Put/Call ratios, IV skew, and Open Interest trends.
3. **Actionable Insights:** Specific expected move ranges or sentiment-driven triggers for traders.
4. **Options Data Table:** A Markdown table summarizing key options metrics and current values."""
            + get_language_instruction()
        )

        return run_tool_analyst(
            llm, state, tools=tools, system_message=system_message,
            report_key="options_report", instrument_context=instrument_context,
        )

    return options_analyst_node
