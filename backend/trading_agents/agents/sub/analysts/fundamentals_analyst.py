from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_sec_filings,
    get_insider_transactions_deep,
    get_language_instruction,
)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.dataflows.config import get_config


@register_analyst(
    key="fundamentals",
    agent_node="Fundamentals Analyst",
    clear_node="Msg Clear Fundamentals",
    tool_node="tools_fundamentals",
    report_key="fundamentals_report",
    tools=[
        get_fundamentals,
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_sec_filings,
        get_insider_transactions_deep,
    ],
)
def create_fundamentals_analyst(llm):
    async def fundamentals_analyst_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_sec_filings,
            get_insider_transactions_deep,
        ]

        system_message = (
            """You are a senior fundamental analyst. Your goal is to assess a company's corporate health and intrinsic value through rigorous financial analysis and regulatory monitoring.

### Analytical Process (Chain-of-Thought):
1. **Data Gathering:** Utilize financial statement tools and `get_sec_filings` to retrieve the latest data and regulatory filings.
2. **Financial Health Audit:** Evaluate key ratios (P/E, Debt-to-Equity, Profit Margins) and statement trends.
3. **Insider Intelligence:** Use `get_insider_transactions_deep` to analyze management sentiment (Are they buying or selling?).
4. **Growth Assessment:** Analyze revenue growth, cash flow stability, and corporate guidance found in SEC reports.
5. **Value Synthesis:** Determine the company's overall fundamental strength and value proposition.

### Guidelines:
- Use `get_fundamentals` for a broad overview.
- Use `get_sec_filings` to find 10-K/10-Q reports for management discussion and analysis (MD&A).
- Prioritize high-volume insider buying as a strong bullish signal.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical fundamental and regulatory findings.
2. **Detailed Analysis:** In-depth review of financial statements and corporate history.
3. **SEC & Insider Sentiment:** Specific breakdown of recent filings and insider trading activity.
4. **Actionable Insights:** Specific strengths, weaknesses, or value-driven triggers.
5. **Financial Data Table:** A Markdown table summarizing key fundamental metrics and current values."""
            + get_language_instruction()
        )

        return await run_tool_analyst(
            llm, state, tools=tools, system_message=system_message,
            report_key="fundamentals_report", instrument_context=instrument_context,
        )

    return fundamentals_analyst_node
