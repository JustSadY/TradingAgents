from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_insider_transactions,
)

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
            data = await route_to_vendor("get_insider_transactions", ticker)
        except Exception:
            data = ""

        data_hash = compute_data_hash("insider", ticker, trade_date, data)
        cached = await check_analyst_cache("insider", ticker, data_hash)
        if cached:
            await emit_cache_hit("insider", ticker)
            return {"messages": [AIMessage(content=cached)], "insider_report": cached}

        tools = _INSIDER_TOOLS

        system_message = """You are a senior insider-activity analyst. Your role is EXCLUSIVELY insider transaction interpretation — you do NOT make buy/sell/hold recommendations. Output only insider-signal observations.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_insider_transactions` to pull recent insider buys and sells.
2. **Signal Assessment:** Distinguish meaningful open-market purchases (a strong conviction signal) from routine sells (option exercises, scheduled 10b5-1 sales, tax-driven disposals) that carry little signal. Classify each transaction as signal/noise.
3. **Clustering:** Look for clusters — several insiders buying around the same time is a much stronger signal than a single transaction. Quantify cluster size and timeframe.
4. **Role Weighting:** Weight signals by insider role — CEO/CFO transactions carry more weight than those of other officers.
5. **Synthesis:** Judge whether insider behaviour confirms or contradicts the broader thesis, with a confidence level.

### Guidelines:
- Open-market BUYS by multiple insiders are the highest-conviction bullish signal.
- A single sell is usually noise; broad, large, unscheduled selling can be a warning.
- Weight transaction size relative to the insider's existing holdings and role (CEO/CFO carry more signal).
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Insider analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each transaction classification.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of the net insider signal (accumulation, distribution, or neutral) with confidence.
2. **Detailed Analysis:** Buy/sell breakdown, who traded, size, significance classification, and role weighting.
3. **Cluster Detection:** Notable clusters of insider activity with timeframe and aggregate signal.
4. **Actionable Insights:** What the insider pattern implies for the trade thesis.
5. **Insider Transactions Table:** A Markdown table of the most relevant recent transactions with classification and signal.""" + get_general_settings_block()

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="insider_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("insider_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("insider", ticker, data_hash, report_text)

        return res

    return insider_analyst_node
