from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_valuation_comparison,
)

# Single source of truth shared by the ToolNode registration and the LLM binding.
_VALUATION_TOOLS = [get_valuation_comparison]


@register_analyst(
    key="valuation",
    agent_node="Valuation Analyst",
    clear_node="Msg Clear Valuation",
    tool_node="tools_valuation",
    report_key="valuation_report",
    tools=_VALUATION_TOOLS,
)
def create_valuation_analyst(llm):

    async def valuation_analyst_node(state):
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _VALUATION_TOOLS

        system_message = """You are a relative-valuation analyst. Your goal is to judge whether the stock is cheap or expensive versus its own sector, not versus the market in the abstract.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_valuation_comparison` to pull the stock's own valuation multiples (Trailing/Forward P/E, Price/Sales, Price/Book, PEG, EV/EBITDA, Profit Margin) alongside the sector ETF's aggregate multiples as a peer proxy.
2. **Relative Read:** For each multiple, judge whether the stock trades at a premium or discount to its sector benchmark, and by roughly how much.
3. **Quality Context:** A premium multiple can be justified by a materially higher profit margin or growth profile; a discount can be a value opportunity or a red flag (weaker fundamentals) — use the margin figure to help distinguish these.
4. **Synthesis:** Form a view on whether the current valuation is a tailwind or headwind for the trade thesis.

### Guidelines:
- The sector ETF's multiples are a *proxy* for peers, not a precise peer set — treat the comparison directionally, not to the decimal.
- Missing multiples (e.g., no PEG for unprofitable companies) are normal; reason from whatever is available.
- A stock trading at a large premium with weaker margins than its sector is the least attractive combination; a discount with comparable or better margins is the most attractive.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of relative valuation (premium/discount, by how much, whether justified).
2. **Detailed Analysis:** Multiple-by-multiple comparison against the sector benchmark.
3. **Actionable Insights:** What the relative valuation implies for the trade thesis.
4. **Valuation Table:** A Markdown table of the stock's multiples next to the sector benchmark's."""

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="valuation_report",
            instrument_context=instrument_context,
        )

    return valuation_analyst_node
