import logging

_logger = logging.getLogger(__name__)
from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_short_interest,
)

_SHORT_INTEREST_TOOLS = [get_short_interest]

@register_analyst(
    key="short_interest",
    agent_node="Short Interest Analyst",
    clear_node="Msg Clear Short Interest",
    tool_node="tools_short_interest",
    report_key="short_interest_report",
    tools=_SHORT_INTEREST_TOOLS,
)
def create_short_interest_analyst(llm):

    async def short_interest_node(state):
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
            data = await route_to_vendor("get_short_interest", ticker)
        except Exception as _e:

            _logger.warning("Data fetch failed in short_interest_analyst: %s", _e)

            data = ""

        data_hash = compute_data_hash("short_interest", ticker, trade_date, data)
        cached = await check_analyst_cache("short_interest", ticker, data_hash)
        if cached:
            await emit_cache_hit("short_interest", ticker)
            return {"messages": [AIMessage(content=cached)], "short_interest_report": cached}

        tools = _SHORT_INTEREST_TOOLS

        system_message = """You are a short-interest analyst. Your role is EXCLUSIVELY short positioning measurement — you do NOT make buy/sell/hold recommendations. Output only short-interest observations.

### Analytical Process (Chain-of-Thought):
1. **Data Retrieval:** Use `get_short_interest` to pull shares short, the short ratio (days to cover), and short % of float.
2. **Crowding Assessment:** High short % of float (>10-20%) plus a high short ratio (many days to cover) means a crowded short — fuel for a squeeze if the thesis turns. Classify squeeze risk as HIGH/MODERATE/LOW.
3. **Trend:** Compare current shares short to the prior month — rising shorts signal growing bearish conviction; falling shorts signal covering. Quantify the percentage change.
4. **Price Context:** Compare short positioning to recent price action — divergence between positioning and price is the most informative signal.
5. **Synthesis:** Judge whether short positioning is a contrarian bullish setup (squeeze potential) or a confirmation of genuine weakness, with confidence level.

### Guidelines:
- Short % of float and days-to-cover together gauge squeeze risk — either alone is weaker.
- A rising short base into strong price action is squeeze fuel; rising shorts into a breakdown confirms the bears.
- Short interest is reported with a lag (bi-monthly); treat it as a slow-moving positioning input, not a timing tool.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Short interest analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet summary of short positioning (crowded/light, rising/falling, squeeze risk) with confidence.
2. **Detailed Analysis:** Shares short, short ratio, short % of float, and the month-over-month change.
3. **Price-Positioning Divergence:** Analysis of how short positioning relates to recent price action.
4. **Actionable Insights:** What the positioning implies for the trade thesis (squeeze setup vs. confirmed weakness).
5. **Short Interest Table:** A Markdown table of the key short-interest figures with interpretation.""" + get_general_settings_block()

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="short_interest_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("short_interest_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("short_interest", ticker, data_hash, report_text)

        return res

    return short_interest_node
