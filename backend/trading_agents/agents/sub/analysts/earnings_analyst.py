import logging

_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_catalyst_calendar,
    get_general_settings_block,
    search_web,
)

_EARNINGS_TOOLS = [search_web, get_catalyst_calendar, run_strategy_backtest]


@register_analyst(
    key="earnings",
    agent_node="Earnings Analyst",
    clear_node="Msg Clear Earnings",
    tool_node="tools_earnings",
    report_key="earnings_report",
    tools=_EARNINGS_TOOLS,
)
def create_earnings_analyst(llm):

    async def earnings_analyst_node(state):
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
            catalyst_data = await route_to_vendor("get_catalyst_calendar", ticker)
        except Exception as _e:

            _logger.warning("Data fetch failed in earnings_analyst: %s", _e)

            catalyst_data = ""
        try:
            end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            search_start = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
            search_data = await route_to_vendor("get_news", ticker, search_start, trade_date)
        except Exception as _e:

            _logger.warning("Data fetch failed in earnings_analyst: %s", _e)

            search_data = ""

        data_hash = compute_data_hash("earnings", ticker, trade_date, catalyst_data, search_data)
        cached = await check_analyst_cache("earnings", ticker, data_hash)
        if cached:
            await emit_cache_hit("earnings", ticker)
            return {"messages": [AIMessage(content=cached)], "earnings_report": cached}

        tools = _EARNINGS_TOOLS

        system_message = """You are a senior earnings and corporate guidance analyst. Your role is EXCLUSIVELY earnings and guidance interpretation — you do NOT make buy/sell/hold recommendations. Output only earnings-quality observations.

### Analytical Process (Chain-of-Thought):
1. **Event Context:** Use `get_catalyst_calendar` to anchor the timeline — when was the last earnings report and when is the next one due.
2. **Targeted Research:** Use `search_web` to find the latest earnings call transcripts, management guidance, and SEC filing summaries.
3. **Management Tone Analysis (structured):** Score the transcript language on these axes and justify each with a quote or paraphrase:
   - *Confidence vs. hedging* — definitive commitments ("we will deliver") vs. hedged language ("we hope", "assuming conditions hold"). Rate as confident/neutral/evasive.
   - *Guidance direction* — raised / maintained / lowered / withdrawn.
   - *Q&A evasiveness* — did executives answer analyst questions directly or deflect?
   - *Surprise-history pattern* — habitual beat-and-raise vs. erratic delivery.
4. **Guidance Assessment:** Review revenue projections, EPS targets, and any revisions to future guidance.
5. **Corporate Synthesis:** Formulate a cohesive narrative on the company's operational trajectory and management's vision, assigning a confidence level.

### Guidelines:
- Search for '[Ticker] latest earnings call transcript summary' or '[Ticker] management guidance'.
- Highlight macro-headwinds mentioned by management.
- Focus on future-looking statements over historical results.
- A tone downgrade (more hedging than the prior quarter) often precedes guidance cuts — flag it even when the numbers still look fine.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Earnings analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical earnings and guidance takeaways, each with confidence.
2. **Management Tone Scorecard:** A short table scoring confidence, guidance direction, Q&A directness, and surprise history (each rated Positive/Neutral/Negative with one-line evidence).
3. **Detailed Analysis:** Nuanced review of management tone, revenue/EPS projections, and strategic guidance.
4. **Actionable Insights:** Specific guidance-driven catalysts or risks for traders to monitor, with confidence.
5. **Earnings & Guidance Table:** A Markdown table summarizing key metrics, guidance changes, management tone, and signal.""" + get_general_settings_block()

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="earnings_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("earnings_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("earnings", ticker, data_hash, report_text)

        return res

    return earnings_analyst_node
