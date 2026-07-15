from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_valuation_comparison,
)

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
        from langchain_core.messages import AIMessage

        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache,
            compute_data_hash,
            emit_cache_hit,
            store_analyst_cache,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor

        instrument_context = build_instrument_context(state["company_of_interest"])
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")

        try:
            data = await route_to_vendor("get_valuation_comparison", ticker)
        except Exception:
            data = ""

        data_hash = compute_data_hash("valuation", ticker, trade_date, data)
        cached = await check_analyst_cache("valuation", ticker, data_hash)
        if cached:
            await emit_cache_hit("valuation", ticker)
            return {"messages": [AIMessage(content=cached)], "valuation_report": cached}

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

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="valuation_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("valuation_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("valuation", ticker, data_hash, report_text)

        return res

    return valuation_analyst_node
