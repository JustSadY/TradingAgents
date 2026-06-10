from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.search_tools import get_crypto_fear_and_greed_index
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_insider_transactions,
    get_language_instruction,
    get_news,
)

# Single source of truth for this analyst's tools: the ToolNode (built from the
# registration) and the LLM binding below must use the same list, otherwise the
# model is bound to tools the ToolNode can run but can never invoke (or vice
# versa).
_NEWS_TOOLS = [get_news, get_global_news, get_insider_transactions, get_crypto_fear_and_greed_index]


@register_analyst(
    key="news",
    agent_node="News Analyst",
    clear_node="Msg Clear News",
    tool_node="tools_news",
    report_key="news_report",
    tools=_NEWS_TOOLS,
)
def create_news_analyst(llm):
    async def news_analyst_node(state):
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)

        tools = _NEWS_TOOLS

        system_message = f"""You are a senior news and macro analyst. Your goal is to identify market-moving events and broader economic trends through rigorous news analysis.

### Analytical Process (Chain-of-Thought):
1. **Targeted Search:** Use `get_news` to find stories specific to the {asset_label} of interest.
2. **Global Context:** Use `get_global_news` to capture macroeconomic trends and geopolitical events.
3. **Corroborating Signals:** For stocks, use `get_insider_transactions` to check for notable insider buying/selling. For crypto assets, use `get_crypto_fear_and_greed_index` to gauge market sentiment.
4. **Event Impact Analysis:** Evaluate how recent news (Earnings, Mergers, Policy changes) will affect price action.
5. **Sentiment Synthesis:** Determine the prevailing narrative shift based on the latest headlines.

### Guidelines:
- Focus on the past week of data.
- Distinguish between "noise" and high-impact "catalysts."
- Provide evidence-based insights with citations where possible.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical news catalysts.
2. **Detailed Analysis:** Comprehensive review of {asset_label}-specific and global macroeconomic developments.
3. **Actionable Insights:** Specific upcoming catalysts or risks for traders to monitor.
4. **News Event Table:** A Markdown table summarizing key events, their dates, impact (High/Med/Low), and a brief description.""" + get_language_instruction()

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="news_report",
            instrument_context=instrument_context,
        )

    return news_analyst_node
