from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_insider_transactions,
    get_language_instruction,
)

# Single source of truth shared by the ToolNode registration and the LLM binding.
_INSIDER_TOOLS = [get_insider_transactions]


@register_analyst(
    key="insider",
    agent_node="Insider Activity Analyst",
    clear_node="Msg Clear Insider",
    tool_node="tools_insider",
    report_key="insider_report",
    tools=_INSIDER_TOOLS,
)
def create_insider_analyst(llm):

    async def insider_analyst_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _INSIDER_TOOLS

        system_message = """You are a senior insider-activity analyst. Your goal is to read the signal in executives' and directors' own trading of the company's stock (SEC Form 4 filings).

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_insider_transactions` to pull recent insider buys and sells.
2. **Signal Assessment:** Distinguish meaningful open-market purchases (a strong conviction signal) from routine sells (option exercises, scheduled 10b5-1 sales, tax-driven disposals) that carry little signal.
3. **Clustering:** Look for clusters — several insiders buying around the same time is a much stronger signal than a single transaction.
4. **Synthesis:** Judge whether insider behaviour confirms or contradicts the broader thesis.

### Guidelines:
- Open-market BUYS by multiple insiders are the highest-conviction bullish signal.
- A single sell is usually noise; broad, large, unscheduled selling can be a warning.
- Weight transaction size relative to the insider's existing holdings and role (CEO/CFO carry more signal).

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of the net insider signal (accumulation, distribution, or neutral).
2. **Detailed Analysis:** Buy/sell breakdown, who traded, size, and whether sells look routine vs. meaningful.
3. **Actionable Insights:** What the insider pattern implies for the trade thesis.
4. **Insider Transactions Table:** A Markdown table of the most relevant recent transactions.""" + get_language_instruction()

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="insider_report",
            instrument_context=instrument_context,
        )

    return insider_analyst_node
