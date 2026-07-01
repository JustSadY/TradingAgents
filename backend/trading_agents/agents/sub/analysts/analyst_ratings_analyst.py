from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_analyst_ratings,
)

# Single source of truth shared by the ToolNode registration and the LLM binding.
_RATINGS_TOOLS = [get_analyst_ratings]


@register_analyst(
    key="ratings",
    agent_node="Analyst Ratings Analyst",
    clear_node="Msg Clear Ratings",
    tool_node="tools_ratings",
    report_key="ratings_report",
    tools=_RATINGS_TOOLS,
)
def create_analyst_ratings_analyst(llm):

    async def analyst_ratings_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _RATINGS_TOOLS

        system_message = """You are a sell-side ratings analyst. Your goal is to read the Wall Street consensus — how professional analysts rate the stock and where they see it going.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_analyst_ratings` to pull the recommendation trend (Strong Buy / Buy / Hold / Sell counts by month) and price targets (low / mean / high / current).
2. **Consensus Direction:** Judge the net tilt (bullish, neutral, bearish) and whether it is strengthening or weakening across recent periods.
3. **Target Dispersion:** Compare the mean target to the current price for implied upside/downside, and note how wide the low-to-high spread is (wide spread = high disagreement / uncertainty).
4. **Contrarian Check:** Extreme, crowded consensus can be a contrarian warning; a lonely upgrade against a bearish crowd can be an early signal.

### Guidelines:
- Anchor implied upside on the mean target vs. the current price; state it as a percentage.
- Distinguish a *shift* in the trend (e.g. downgrades appearing) from a static rating — the change carries more signal than the level.
- Analyst targets lag price and herd; treat them as one input, not gospel.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of the consensus (direction, implied upside, level of agreement).
2. **Detailed Analysis:** Recommendation trend over time, price-target spread, and implied upside/downside.
3. **Actionable Insights:** What the consensus (and any recent shift in it) implies for the trade thesis.
4. **Ratings Table:** A Markdown table of the recommendation trend and key price-target figures."""

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="ratings_report",
            instrument_context=instrument_context,
        )

    return analyst_ratings_node
