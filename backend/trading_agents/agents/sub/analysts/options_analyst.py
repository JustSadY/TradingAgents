import logging

_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_options_data,
)

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
            end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            start_dt = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")
            data = await route_to_vendor("get_news", ticker, start_dt, trade_date)
        except Exception as _e:

            _logger.warning("Data fetch failed in options_analyst: %s", _e)

            data = ""

        data_hash = compute_data_hash("options", ticker, trade_date, data)
        cached = await check_analyst_cache("options", ticker, data_hash)
        if cached:
            await emit_cache_hit("options", ticker)
            return {"messages": [AIMessage(content=cached)], "options_report": cached}

        tools = _OPTIONS_TOOLS

        system_message = """You are a senior options and derivatives analyst. Your role is EXCLUSIVELY options market interpretation — you do NOT make buy/sell/hold recommendations. Output only data-driven observations.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_options_data` to fetch latest options chain, including Put/Call ratios, Implied Volatility (IV), and Open Interest.
2. **Sentiment Assessment:** Analyze the Put/Call ratio (P/C > 1 is typically bearish/hedging; P/C < 0.7 is typically bullish). State the reading quantitatively.
3. **Volatility Interpretation:** Compare IV to historical levels to assess expected price movement magnitude. Classify as elevated/normal/depressed.
4. **Skew Analysis:** Examine IV skew across strikes — put-side elevation signals hedging demand; call-side skew signals upside speculation.
5. **Positioning Synthesis:** Formulate what the "smart money" is pricing in via the derivatives market, assigning a confidence level.

### Guidelines:
- High Put/Call ratios can indicate bearishness or heavy hedging — distinguish between them.
- High Implied Volatility (IV) suggests the market expects significant price swings (e.g., around earnings).
- Look for imbalances in Open Interest between calls and puts.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Options analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical options-derived sentiment and volatility signals, each with confidence.
2. **Detailed Analysis:** Nuanced interpretation of Put/Call ratios, IV skew, Open Interest trends, and expected move.
3. **Positioning Assessment:** What the options market implies about institutional positioning and sentiment.
4. **Key Levels:** Implied move range, max pain, and significant open interest concentrations.
5. **Options Data Table:** A Markdown table summarizing key options metrics, current values, and signal interpretation.""" + get_general_settings_block()

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
