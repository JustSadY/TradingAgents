from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
)
from backend.trading_agents.dataflows.config import get_config
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.data.chart_tools import (
    add_chart_annotation,
    add_custom_indicator,
    get_vision_chart_analysis,
    get_mtf_trend,
)


@register_analyst(
    key="market",
    agent_node="Market Analyst",
    clear_node="Msg Clear Market",
    tool_node="tools_market",
    report_key="market_report",
    tools=[
        get_stock_data,
        get_indicators,
        add_chart_annotation,
        add_custom_indicator,
        get_vision_chart_analysis,
        get_mtf_trend,
    ],
)
def create_market_analyst(llm):

    async def market_analyst_node(state):
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [
            get_stock_data,
            get_indicators,
            add_chart_annotation,
            add_custom_indicator,
            get_vision_chart_analysis,
            get_mtf_trend,
        ]

        system_message = (
            """You are a senior market analyst. Your goal is to provide a high-conviction, data-driven technical analysis report.

### Analytical Process (Chain-of-Thought):
1. **Data Extraction:** Retrieve raw price and volume data using `get_stock_data`.
2. **Indicator Selection & Visual Recognition:** Select indicators. Call `get_vision_chart_analysis` to let the vision system review visual patterns (like head and shoulders or triangles) on the chart.
3. **Multi-Timeframe Trend:** Call `get_mtf_trend` for timeframe (e.g. '1wk' or '1mo') to align with higher-timeframe trend lines.
4. **Custom Indicators & Annotations:** If you notice special price levels or want to specify custom indicators (like (Close - SMA(20)) / STD(20)), use `add_custom_indicator` and `add_chart_annotation` to draw them on the interactive chart.
5. **Contextual Synthesis:** Combine all signals into a cohesive market narrative.

### Indicator Reference:
Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence.
- macds: MACD Signal: An EMA smoothing of the MACD line.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions (70/30 thresholds).

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA.
- boll_ub: Bollinger Upper Band (2 std dev above).
- boll_lb: Bollinger Lower Band (2 std dev below).
- atr: ATR: Measures volatility for stop-loss and sizing.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume.

### Guidelines:
- Avoid redundancy (e.g., don't select both rsi and stochrsi).
- Call `get_stock_data` first, then `get_indicators` with the exact parameter names.
- **IMPORTANT:** If data retrieval fails, output a clear error report stating data is unavailable.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical findings.
2. **Detailed Analysis:** Nuanced interpretation of trends, momentum, and volatility with supporting evidence.
3. **Actionable Insights:** Specific technical levels or triggers to watch.
4. **Data Table:** A Markdown table summarizing all calculated indicators and their current values."""
            + get_language_instruction()
        )

        return await run_tool_analyst(
            llm, state, tools=tools, system_message=system_message,
            report_key="market_report", instrument_context=instrument_context,
        )

    return market_analyst_node
