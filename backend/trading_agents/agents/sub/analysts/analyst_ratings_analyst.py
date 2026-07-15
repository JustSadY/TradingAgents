from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_analyst_ratings,
)

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
        from langchain_core.messages import AIMessage

        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache,
            compute_data_hash,
            emit_cache_hit,
            store_analyst_cache,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor

        instrument_context = build_instrument_context(state["company_of_interest"])
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")

        try:
            data = await route_to_vendor("get_analyst_ratings", ticker)
        except Exception:
            data = ""

        data_hash = compute_data_hash("ratings", ticker, trade_date, data)
        cached = await check_analyst_cache("ratings", ticker, data_hash)
        if cached:
            await emit_cache_hit("ratings", ticker)
            return {"messages": [AIMessage(content=cached)], "ratings_report": cached}

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

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="ratings_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("ratings_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("ratings", ticker, data_hash, report_text)

        return res

    return analyst_ratings_node
