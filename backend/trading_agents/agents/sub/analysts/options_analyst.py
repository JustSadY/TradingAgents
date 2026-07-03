from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_options_data,
)
from datetime import datetime, timedelta

# Single source of truth shared by the ToolNode registration and the LLM binding.
_OPTIONS_TOOLS = [get_options_data]


@register_analyst(
    key="options",
    agent_node="Options Analyst",
    clear_node="Msg Clear Options",
    tool_node="tools_options",
    report_key="options_report",
    tools=_OPTIONS_TOOLS,
)
def create_options_analyst(llm):

    async def options_analyst_node(state):
        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache, store_analyst_cache, compute_data_hash, emit_cache_hit,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor
        from langchain_core.messages import AIMessage

        instrument_context = build_instrument_context(state["company_of_interest"])
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")

        try:
            end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            start_dt = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")
            data = await route_to_vendor("get_news", ticker, start_dt, trade_date)
        except Exception:
            data = ""

        data_hash = compute_data_hash("options", ticker, trade_date, data)
        cached = await check_analyst_cache("options", ticker, data_hash)
        if cached:
            await emit_cache_hit("options", ticker)
            return {"messages": [AIMessage(content=cached)], "options_report": cached}

        tools = _OPTIONS_TOOLS

        system_message = """You are a senior options and derivatives analyst. Your goal is to decode market expectations and institutional positioning through options chain analysis.

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

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="options_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("options_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("options", ticker, data_hash, report_text)

        return res

    return options_analyst_node
