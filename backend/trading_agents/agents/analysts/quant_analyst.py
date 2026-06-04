from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_quant_data,
    get_language_instruction,
)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.utils.chart_tools import (
    add_chart_annotation,
    add_custom_indicator,
    get_vision_chart_analysis,
    get_mtf_trend,
)


@register_analyst(
    key="quant",
    agent_node="Quant Analyst",
    clear_node="Msg Clear Quant",
    tool_node="tools_quant",
    report_key="quant_report",
    tools=[
        get_quant_data,
        add_chart_annotation,
        add_custom_indicator,
        get_vision_chart_analysis,
        get_mtf_trend,
    ],
)
def create_quant_analyst(llm):

    def quant_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_quant_data,
            add_chart_annotation,
            add_custom_indicator,
            get_vision_chart_analysis,
            get_mtf_trend,
        ]

        system_message = (
            """You are a senior quantitative analyst. Your goal is to provide a statistically rigorous assessment of an asset's risk-return profile and market correlation.

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
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "quant_report": report,
        }

    return quant_analyst_node
