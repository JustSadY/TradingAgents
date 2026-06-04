from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_macro_data,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config
from tradingagents.agents.analyst_registry import register_analyst


@register_analyst(
    key="macro",
    agent_node="Macro Analyst",
    clear_node="Msg Clear Macro",
    tool_node="tools_macro",
    report_key="macro_report",
    tools=[get_macro_data],
)
def create_macro_analyst(llm):

    def macro_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_macro_data,
        ]

        system_message = (
            """You are a senior macroeconomic analyst. Your goal is to interpret the broader economic climate and its ripple effects on financial markets.

### Analytical Process (Chain-of-Thought):
1. **Data Acquisition:** Use `get_macro_data` to fetch latest values for VIX, 10-Year Yield, Crude Oil, Gold, etc.
2. **Indicator Interpretation:** Analyze what these levels mean (e.g., VIX > 20 indicates high fear; rising yields pressure growth valuations).
3. **Inter-market Correlation:** Assess how these factors specifically impact the sector and instrument under review.
4. **Economic Synthesis:** Formulate a cohesive macro narrative (e.g., Risk-On/Risk-Off, Inflationary/Deflationary).

### Guidelines:
- High VIX suggests a risk-off environment.
- Rising yields typically pressure growth stocks but may benefit financials.
- Commodity prices (Oil/Gold) signal inflation or geopolitical stress.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the dominant macro regime and its bias.
2. **Detailed Analysis:** Nuanced breakdown of key indicators and their specific influence on the market.
3. **Actionable Insights:** Potential macro-driven triggers or headwinds for the trader to consider.
4. **Macro Data Table:** A Markdown table summarizing all fetched macro indicators and their current levels."""
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
            "macro_report": report,
        }

    return macro_analyst_node
