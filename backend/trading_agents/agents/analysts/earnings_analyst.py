from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    search_web,
    get_language_instruction,
)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.utils.analyst_node_factory import run_tool_analyst


@register_analyst(
    key="earnings",
    agent_node="Earnings Analyst",
    clear_node="Msg Clear Earnings",
    tool_node="tools_earnings",
    report_key="earnings_report",
    tools=[search_web],
)
def create_earnings_analyst(llm):

    def earnings_analyst_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            search_web,
        ]

        system_message = (
            """You are a senior earnings and corporate guidance analyst. Your goal is to extract key insights from management communication and financial filings.

### Analytical Process (Chain-of-Thought):
1. **Targeted Research:** Use `search_web` to find the latest earnings call transcripts, management guidance, and SEC filing summaries.
2. **Sentiment & Tone Analysis:** Evaluate the tone of the CEO/CFO and identify areas of high confidence vs. caution.
3. **Guidance Assessment:** Review revenue projections, EPS targets, and any revisions to future guidance.
4. **Corporate Synthesis:** Formulate a cohesive narrative on the company's operational trajectory and management's vision.

### Guidelines:
- Search for '[Ticker] latest earnings call transcript summary' or '[Ticker] management guidance'.
- Highlight macro-headwinds mentioned by management.
- Focus on future-looking statements over historical results.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical earnings and guidance takeaways.
2. **Detailed Analysis:** Nuanced review of management tone, revenue/EPS projections, and strategic guidance.
3. **Actionable Insights:** Specific guidance-driven catalysts or risks for traders to monitor.
4. **Earnings & Guidance Table:** A Markdown table summarizing key metrics, guidance changes, and management tone."""
            + get_language_instruction()
        )

        return run_tool_analyst(
            llm, state, tools=tools, system_message=system_message,
            report_key="earnings_report", instrument_context=instrument_context,
        )

    return earnings_analyst_node
