from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_catalyst_calendar,
)

_CATALYST_TOOLS = [get_catalyst_calendar]


@register_analyst(
    key="catalyst",
    agent_node="Catalyst Calendar Analyst",
    clear_node="Msg Clear Catalyst",
    tool_node="tools_catalyst",
    report_key="catalyst_report",
    tools=_CATALYST_TOOLS,
)
def create_catalyst_analyst(llm):

    async def catalyst_analyst_node(state):
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
            data = await route_to_vendor("get_catalyst_calendar", ticker)
        except Exception:
            data = ""

        data_hash = compute_data_hash("catalyst", ticker, trade_date, data)
        cached = await check_analyst_cache("catalyst", ticker, data_hash)
        if cached:
            await emit_cache_hit("catalyst", ticker)
            return {"messages": [AIMessage(content=cached)], "catalyst_report": cached}

        tools = _CATALYST_TOOLS

        system_message = """You are a senior event-risk analyst. Your role is EXCLUSIVELY event-risk mapping — you do NOT make buy/sell/hold recommendations. Output only catalyst calendar observations.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_catalyst_calendar` to pull the next earnings date, ex-dividend date, and scheduled earnings history with estimates.
2. **Proximity Assessment:** Compute how close the trade date is to each event. Anything within ~5 trading days is a HIGH risk window; within ~2 weeks is MODERATE.
3. **Asymmetry Analysis:** Judge whether the event skews risk up or down (e.g. a habitual earnings-beater into low expectations vs. a stretched valuation into a binary print). Assign confidence to the asymmetry assessment.
4. **Positioning Guidance:** Translate the event map into sizing/leverage advice: binary events argue for reduced size, reduced leverage, and wider stops.

### Guidelines:
- Earnings within the risk window is the single most important flag — flag it explicitly with risk level.
- If no catalyst falls inside the window, state that clearly; absence of event risk is itself actionable.
- Never invent dates: use only what the tool returns.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Event-risk analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each proximity and asymmetry assessment.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary: nearest catalyst, its distance from the trade date, the implied risk window (HIGH/MODERATE/CLEAR), and confidence.
2. **Detailed Analysis:** Event-by-event review with dates, estimates, and the asymmetry of each.
3. **Risk Window Map:** Timeline of upcoming events with risk ratings and confidence for each window.
4. **Actionable Insights:** Concrete sizing/leverage/stop adjustments for trading through (or around) the events.
5. **Catalyst Table:** A Markdown table of upcoming events with dates, risk ratings, and confidence."""

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="catalyst_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("catalyst_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("catalyst", ticker, data_hash, report_text)

        return res

    return catalyst_analyst_node
