import logging

_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.chart_tools import (
    add_chart_annotation,
    add_custom_indicator,
    get_mtf_trend,
    get_vision_chart_analysis,
)
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_quant_data,
)

_QUANT_TOOLS = [
    get_quant_data,
    add_chart_annotation,
    add_custom_indicator,
    get_vision_chart_analysis,
    get_mtf_trend,
]


@register_analyst(
    key="quant",
    agent_node="Quant Analyst",
    clear_node="Msg Clear Quant",
    tool_node="tools_quant",
    report_key="quant_report",
    tools=_QUANT_TOOLS,
)
def create_quant_analyst(llm):

    async def quant_analyst_node(state):
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
            start_dt = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
            data = await route_to_vendor("get_stock_data", ticker, start_dt, trade_date)
        except Exception as _e:

            _logger.warning("Data fetch failed in quant_analyst: %s", _e)

            data = ""

        data_hash = compute_data_hash("quant", ticker, trade_date, data)
        cached = await check_analyst_cache("quant", ticker, data_hash)
        if cached:
            await emit_cache_hit("quant", ticker)
            return {"messages": [AIMessage(content=cached)], "quant_report": cached}

        tools = _QUANT_TOOLS

        system_message = """You are a senior quantitative analyst. Your role is EXCLUSIVELY quantitative risk assessment — you do NOT make buy/sell/hold recommendations. Output only statistically-grounded observations.

### Analytical Process (Chain-of-Thought):
1. **Data Acquisition:** Use `get_quant_data` to retrieve statistical metrics (Beta, Sharpe Ratio, Volatility, Max Drawdown).
2. **Visual Analysis & Higher Timeframe Trend:** Call `get_vision_chart_analysis` to evaluate the chart visually, and `get_mtf_trend` to align with macro trend lines.
3. **Custom Indicator Design:** If standard indicators are insufficient, create custom quantitative signals using the `add_custom_indicator` tool (e.g., `(Close - SMA(20)) / STD(20)`) and mark key quantitative levels using `add_chart_annotation`.
4. **Risk-Adjusted Evaluation:** Analyze the Sharpe Ratio to determine if returns justify the volatility risk. Classify as strong/adequate/poor.
5. **Market Correlation Study:** Use Beta to assess how the asset moves relative to the benchmark (SPY). State what the correlation implies for diversification.
6. **Statistical Synthesis:** Formulate a quantitative conclusion on the asset's risk profile and efficiency with a confidence level.

### Guidelines:
- Beta > 1 indicates higher sensitivity to market moves; Beta < 1 indicates lower sensitivity.
- A high Sharpe Ratio (> 1) indicates good risk-adjusted performance.
- Volatility metrics should be contextualized within the sector average.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Quantitative analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical quantitative risk and return signals, each with confidence.
2. **Detailed Analysis:** Nuanced interpretation of statistical metrics, market correlation, and risk efficiency.
3. **Portfolio Fit Assessment:** How the asset's quant profile fits into broader portfolio context (diversification, risk contribution).
4. **Risk Flags:** Any statistical red flags (extreme volatility, negative Sharpe, high drawdown risk).
5. **Quantitative Data Table:** A Markdown table summarizing all calculated quant metrics, current values, and signal interpretation.""" + get_general_settings_block()

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="quant_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("quant_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("quant", ticker, data_hash, report_text)

        return res

    return quant_analyst_node
