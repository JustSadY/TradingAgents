from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_institutional_holdings,
)

_OWNERSHIP_TOOLS = [get_institutional_holdings]


@register_analyst(
    key="ownership",
    agent_node="Institutional Ownership Analyst",
    clear_node="Msg Clear Ownership",
    tool_node="tools_ownership",
    report_key="ownership_report",
    tools=_OWNERSHIP_TOOLS,
)
def create_institutional_analyst(llm):

    async def institutional_analyst_node(state):
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
            data = await route_to_vendor("get_institutional_holdings", ticker)
        except Exception:
            data = ""

        data_hash = compute_data_hash("ownership", ticker, trade_date, data)
        cached = await check_analyst_cache("ownership", ticker, data_hash)
        if cached:
            await emit_cache_hit("ownership", ticker)
            return {"messages": [AIMessage(content=cached)], "ownership_report": cached}

        tools = _OWNERSHIP_TOOLS

        system_message = """You are a senior institutional-ownership analyst. Your role is EXCLUSIVELY ownership structure interpretation — you do NOT make buy/sell/hold recommendations. Output only ownership observations.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_institutional_holdings` to pull institutional ownership, the insider/institution/float breakdown, and top fund holders.
2. **Concentration Assessment:** Gauge how concentrated ownership is — heavy institutional ownership implies conviction but also crowding risk. Classify as concentrated/moderate/diffuse.
3. **Holder Quality:** Note marquee long-term holders vs. fast-money funds where the data allows. Classify holder quality as strong/mixed/weak.
4. **Trend Assessment:** Compare current ownership levels to prior periods if available — rising institutional interest vs. distribution.
5. **Synthesis:** Judge whether institutional positioning supports or undercuts the thesis, with confidence level.

### Guidelines:
- Very high institutional ownership (>90%) can mean limited remaining buying power and crowding risk.
- Low institutional ownership can mean an under-the-radar opportunity OR a quality/liquidity concern.
- Treat point-in-time 13F data as lagging; emphasise the standing structure, not precise timing.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Ownership analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of the institutional ownership picture, concentration level, holder quality, and confidence.
2. **Detailed Analysis:** Ownership concentration, notable holders, holder quality assessment, and crowding/liquidity considerations.
3. **Trend Observation:** Directional shift in institutional interest (accumulation/distribution/stable).
4. **Actionable Insights:** What institutional positioning implies for the trade thesis and risk.
5. **Ownership Table:** A Markdown table of the major and institutional holders with ownership stakes."""

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="ownership_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("ownership_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("ownership", ticker, data_hash, report_text)

        return res

    return institutional_analyst_node
