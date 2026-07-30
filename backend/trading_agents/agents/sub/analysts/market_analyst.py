import logging

_logger = logging.getLogger(__name__)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.data.chart_tools import (
    add_chart_annotation,
    add_custom_indicator,
    get_mtf_trend,
    get_vision_chart_analysis,
)
from backend.trading_agents.agents.data.search_tools import search_web
from backend.trading_agents.agents.data.technical_indicators_tools import collect_indicators
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_indicators,
    get_stock_data,
)

_MARKET_TOOLS = [
    get_stock_data,
    get_indicators,
    add_chart_annotation,
    add_custom_indicator,
    get_vision_chart_analysis,
    get_mtf_trend,
    run_strategy_backtest,
    search_web,
]


@register_analyst(
    key="market",
    agent_node="Market Analyst",
    clear_node="Msg Clear Market",
    tool_node="tools_market",
    report_key="market_report",
    tools=_MARKET_TOOLS,
)
def create_market_analyst(llm):

    async def market_analyst_node(state):

        from datetime import datetime, timedelta

        from langchain_core.messages import AIMessage

        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache,
            compute_data_hash,
            emit_cache_hit,
            store_analyst_cache,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor

        asset_type = state.get("asset_type", "stock")

        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)

        tools = _MARKET_TOOLS

        system_message = """You are a senior market technical analyst. Your role is EXCLUSIVELY technical analysis — you do NOT make buy/sell/hold recommendations. Output only data-driven observations.

### Analytical Process (Chain-of-Thought):
1. **Data Extraction:** Retrieve raw price and volume data using `get_stock_data`.
2. **Indicator Selection & Visual Recognition:** Select indicators. Call `get_vision_chart_analysis` to let the vision system review visual patterns (like head and shoulders or triangles) on the chart.
3. **Multi-Timeframe Trend:** Call `get_mtf_trend` for timeframe (e.g. '1wk' or '1mo') to align with higher-timeframe trend lines.
4. **Custom Indicators & Annotations:** If you notice special price levels or want to specify custom indicators (like (Close - SMA(20)) / STD(20)), use `add_custom_indicator` and `add_chart_annotation` to draw them on the interactive chart.
5. **Signal Contextualization:** For each signal, state: direction (bullish/bearish/neutral), strength (strong/moderate/weak), and supporting evidence.

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
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Your output is technical evidence only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical findings, each with confidence level.
2. **Detailed Analysis:** Nuanced interpretation of trends, momentum, and volatility with supporting evidence and specific price levels.
3. **Identified Patterns:** Chart patterns detected (if any), with direction and confidence.
4. **Key Levels:** Identified support, resistance, and volume-weighted price levels.
5. **Data Table:** A Markdown table summarizing all calculated indicators, their current values, and signal interpretation.""" + get_general_settings_block()

        ticker = state.get("company_of_interest", "")

        trade_date = state.get("trade_date", "")

        try:
            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")

            start_dt = trade_dt - timedelta(days=365)

            start_date_str = start_dt.strftime("%Y-%m-%d")

        except Exception as _e:


            _logger.warning("Data fetch failed in market_analyst: %s", _e)


            start_date_str = trade_date

        try:
            stock_data = await route_to_vendor("get_stock_data", ticker, start_date_str, trade_date)

        except Exception as _e:


            _logger.warning("Data fetch failed in market_analyst: %s", _e)


            stock_data = ""

        try:
            from backend.trading_agents.dataflows.config import get_config

            server_tool_settings = get_config().get("runtime_tool_context", {}).get("server_settings", {})
            lookback_days = int(
                server_tool_settings.get("technical_indicators", {})
                .get("settings", {})
                .get("default_lookback_days", 30)
                or 30
            )

            indicators_data = await collect_indicators(
                ticker,
                "close_50_sma,close_200_sma,close_10_ema,macd,macds,macdh,rsi,boll,boll_ub,boll_lb,atr,vwma",
                trade_date,
                lookback_days,
            )

        except Exception as _e:


            _logger.warning("Data fetch failed in market_analyst: %s", _e)


            indicators_data = ""

        data_hash = compute_data_hash("market", ticker, trade_date, stock_data, indicators_data)

        cached_report = await check_analyst_cache("market", ticker, data_hash)

        if cached_report:
            await emit_cache_hit("market", ticker)

            return {
                "messages": [AIMessage(content=cached_report)],
                "market_report": cached_report,
            }

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="market_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("market_report", "")

        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("market", ticker, data_hash, report_text)

        return res

    return market_analyst_node
