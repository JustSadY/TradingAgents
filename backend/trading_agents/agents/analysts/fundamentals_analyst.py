from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
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
from tradingagents.agents.analyst_registry import register_analyst
from tradingagents.dataflows.config import get_config


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
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
