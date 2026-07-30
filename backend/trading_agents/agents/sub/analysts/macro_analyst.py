import logging

_logger = logging.getLogger(__name__)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.search_tools import search_web
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_macro_data,
)

_MACRO_TOOLS = [get_macro_data, search_web]


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
        except Exception as _e:

            _logger.warning("Data fetch failed in macro_analyst: %s", _e)

            data = ""

        data_hash = compute_data_hash("macro", ticker, trade_date, data)
        cached = await check_analyst_cache("macro", ticker, data_hash)
        if cached:
            await emit_cache_hit("macro", ticker)
            return {"messages": [AIMessage(content=cached)], "macro_report": cached}

        tools = _MACRO_TOOLS

        system_message = """You are a senior macroeconomic analyst. Your role is EXCLUSIVELY macro analysis — you do NOT make buy/sell/hold recommendations. Output only macro regime observations.

### Analytical Process (Chain-of-Thought):
1. **Data Acquisition:** Use `get_macro_data` to fetch latest values for VIX, 10-Year Yield, Crude Oil, Gold, etc.
2. **Quantitative Interpretation:** For each indicator, state: current level, historical percentile, trend direction, and what it signals.
3. **Regime Classification:** Classify the current macro regime (Risk-On/Risk-Off, Inflationary/Deflationary, Expansion/Contraction).
4. **Inter-market Correlation:** Assess how these factors specifically impact the sector and instrument under review.
5. **Economic Synthesis:** Formulate a cohesive macro narrative, assigning a confidence level.

### Guidelines:
- High VIX (>20) suggests elevated fear and risk-off environment.
- Rising yields typically pressure growth stocks but may benefit financials.
- Commodity prices (Oil/Gold) signal inflation or geopolitical stress.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Macro analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the dominant macro regime, its bias, and confidence level.
2. **Regime Classification:** Explicit statement of current macro regime with supporting evidence.
3. **Detailed Analysis:** Nuanced breakdown of key indicators, their historical context, and specific influence on the market.
4. **Instrument Impact:** How the macro environment specifically affects the asset under review (sector sensitivity).
5. **Actionable Insights:** Potential macro-driven triggers or headwinds for the trader to consider.
6. **Macro Data Table:** A Markdown table summarizing all fetched macro indicators, current levels, historical percentile, and interpretation.""" + get_general_settings_block()

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
