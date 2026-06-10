from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_catalyst_calendar,
    get_language_instruction,
)


# Single source of truth shared by the ToolNode registration and the LLM binding.
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
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _CATALYST_TOOLS

        system_message = """You are a senior event-risk analyst. Your goal is to map the known catalysts ahead of this instrument and translate them into concrete risk-window guidance for the trade.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_catalyst_calendar` to pull the next earnings date, ex-dividend date, and scheduled earnings history with estimates.
2. **Proximity Assessment:** Compute how close the trade date is to each event. Anything within ~5 trading days is a HIGH risk window; within ~2 weeks is MODERATE.
3. **Asymmetry Analysis:** Judge whether the event skews risk up or down (e.g. a habitual earnings-beater into low expectations vs. a stretched valuation into a binary print).
4. **Positioning Guidance:** Translate the event map into sizing/leverage advice: binary events argue for reduced size, reduced leverage, and wider stops.

### Guidelines:
- Earnings within the risk window is the single most important flag — say so explicitly and recommend capping leverage at 1x-2x through the print.
- If no catalyst falls inside the window, state that clearly; absence of event risk is itself actionable.
- Never invent dates: use only what the tool returns.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary: nearest catalyst, its distance from the trade date, and the implied risk window (HIGH/MODERATE/CLEAR).
2. **Detailed Analysis:** Event-by-event review with dates, estimates, and the asymmetry of each.
3. **Actionable Insights:** Concrete sizing/leverage/stop adjustments for trading through (or around) the events.
4. **Catalyst Table:** A Markdown table of upcoming events with dates and risk ratings.""" + get_language_instruction()

        return await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="catalyst_report",
            instrument_context=instrument_context,
        )

    return catalyst_analyst_node
