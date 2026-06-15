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
    get_quant_data,
)

# Single source of truth shared by the ToolNode registration and the LLM binding.
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
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _QUANT_TOOLS

        system_message = """You are a senior quantitative analyst. Your goal is to provide a statistically rigorous assessment of an asset's risk-return profile and market correlation.

### Analytical Process (Chain-of-Thought):
1. **Data Acquisition:** Use `get_quant_data` to retrieve statistical metrics (Beta, Sharpe Ratio, Volatility, Max Drawdown).
2. **Visual Analysis & Higher Timeframe Trend:** Call `get_vision_chart_analysis` to evaluate the chart visually, and `get_mtf_trend` to align with macro trend lines.
3. **Custom Indicator Design:** If standard indicators are insufficient, create custom quantitative signals using the `add_custom_indicator` tool (e.g., `(Close - SMA(20)) / STD(20)`) and mark key quantitative levels using `add_chart_annotation`.
4. **Risk-Adjusted Evaluation:** Analyze the Sharpe Ratio to determine if returns justify the volatility risk.
5. **Market Correlation Study:** Use Beta to assess how the asset moves relative to the benchmark (SPY).
6. **Statistical Synthesis:** Formulate a quantitative conclusion on the asset's risk profile and efficiency.

### Guidelines:
- Beta > 1 indicates higher sensitivity to market moves; Beta < 1 indicates lower sensitivity.
- A high Sharpe Ratio (> 1) indicates good risk-adjusted performance.
- Volatility metrics should be contextualized within the sector average.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical quantitative risk and return signals.
2. **Detailed Analysis:** Nuanced interpretation of statistical metrics, market correlation, and risk efficiency.
3. **Actionable Insights:** Specific risk-adjusted triggers or portfolio fit considerations for traders.
4. **Quantitative Data Table:** A Markdown table summarizing all calculated quant metrics and their current values."""

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="quant_report",
            instrument_context=instrument_context,
        )

    return quant_analyst_node
