from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    search_web,
    get_language_instruction,
)
from backend.trading_agents.agents.analyst_registry import register_analyst


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
        current_date = state["trade_date"]
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
            "earnings_report": report,
        }

    return earnings_analyst_node
