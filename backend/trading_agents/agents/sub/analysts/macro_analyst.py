from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_macro_data,
)

_MACRO_TOOLS = [get_macro_data]


@register_analyst(
    key="macro",
    agent_node="Macro Analyst",
    clear_node="Msg Clear Macro",
    tool_node="tools_macro",
    report_key="macro_report",
    tools=_MACRO_TOOLS,
)
def create_macro_analyst(llm):

    async def macro_analyst_node(state):
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
            data = await route_to_vendor("get_global_news", trade_date, 1, 10)
        except Exception:
            data = ""

        data_hash = compute_data_hash("macro", ticker, trade_date, data)
        cached = await check_analyst_cache("macro", ticker, data_hash)
        if cached:
            await emit_cache_hit("macro", ticker)
            return {"messages": [AIMessage(content=cached)], "macro_report": cached}

        tools = _MACRO_TOOLS

        system_message = """You are a senior macroeconomic analyst. Your goal is to interpret the broader economic climate and its ripple effects on financial markets.

### Analytical Process (Chain-of-Thought):
1. **Data Acquisition:** Use `get_macro_data` to fetch latest values for VIX, 10-Year Yield, Crude Oil, Gold, etc.
2. **Indicator Interpretation:** Analyze what these levels mean (e.g., VIX > 20 indicates high fear; rising yields pressure growth valuations).
3. **Inter-market Correlation:** Assess how these factors specifically impact the sector and instrument under review.
4. **Economic Synthesis:** Formulate a cohesive macro narrative (e.g., Risk-On/Risk-Off, Inflationary/Deflationary).

### Guidelines:
- High VIX suggests a risk-off environment.
- Rising yields typically pressure growth stocks but may benefit financials.
- Commodity prices (Oil/Gold) signal inflation or geopolitical stress.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the dominant macro regime and its bias.
2. **Detailed Analysis:** Nuanced breakdown of key indicators and their specific influence on the market.
3. **Actionable Insights:** Potential macro-driven triggers or headwinds for the trader to consider.
4. **Macro Data Table:** A Markdown table summarizing all fetched macro indicators and their current levels."""

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="macro_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("macro_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("macro", ticker, data_hash, report_text)

        return res

    return macro_analyst_node
