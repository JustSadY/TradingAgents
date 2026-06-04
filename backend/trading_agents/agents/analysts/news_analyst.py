from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_insider_transactions,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.search_tools import get_crypto_fear_and_greed_index
from tradingagents.dataflows.config import get_config
from tradingagents.agents.analyst_registry import register_analyst


@register_analyst(
    key="news",
    agent_node="News Analyst",
    clear_node="Msg Clear News",
    tool_node="tools_news",
    report_key="news_report",
    tools=[get_news, get_global_news, get_insider_transactions, get_crypto_fear_and_greed_index],
)
def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            f"""You are a senior news and macro analyst. Your goal is to identify market-moving events and broader economic trends through rigorous news analysis.

### Analytical Process (Chain-of-Thought):
1. **Targeted Search:** Use `get_news` to find stories specific to the {asset_label} of interest.
2. **Global Context:** Use `get_global_news` to capture macroeconomic trends and geopolitical events.
3. **Event Impact Analysis:** Evaluate how recent news (Earnings, Mergers, Policy changes) will affect price action.
4. **Sentiment Synthesis:** Determine the prevailing narrative shift based on the latest headlines.

### Guidelines:
- Focus on the past week of data.
- Distinguish between "noise" and high-impact "catalysts."
- Provide evidence-based insights with citations where possible.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical news catalysts.
2. **Detailed Analysis:** Comprehensive review of {asset_label}-specific and global macroeconomic developments.
3. **Actionable Insights:** Specific upcoming catalysts or risks for traders to monitor.
4. **News Event Table:** A Markdown table summarizing key events, their dates, impact (High/Med/Low), and a brief description."""
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
            "news_report": report,
        }

    return news_analyst_node
