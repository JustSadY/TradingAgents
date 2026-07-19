from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions_deep,
    get_sec_filings,
)

_FUNDAMENTALS_TOOLS = [
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_sec_filings,
    get_insider_transactions_deep,
]


@register_analyst(
    key="fundamentals",
    agent_node="Fundamentals Analyst",
    clear_node="Msg Clear Fundamentals",
    tool_node="tools_fundamentals",
    report_key="fundamentals_report",
    tools=_FUNDAMENTALS_TOOLS,
)
def create_fundamentals_analyst(llm):

    async def fundamentals_analyst_node(state):

        from langchain_core.messages import AIMessage

        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache,
            compute_data_hash,
            emit_cache_hit,
            store_analyst_cache,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor

        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = _FUNDAMENTALS_TOOLS

        system_message = """You are a senior fundamental analyst. Your role is EXCLUSIVELY fundamental analysis — you do NOT make buy/sell/hold recommendations. Output only data-driven observations.

### Analytical Process (Chain-of-Thought):
1. **Data Gathering:** Utilize financial statement tools and `get_sec_filings` to retrieve the latest data and regulatory filings.
2. **Financial Health Audit:** Evaluate key ratios (P/E, Debt-to-Equity, Profit Margins) and statement trends. Compare each metric to industry averages.
3. **Insider Intelligence:** Use `get_insider_transactions_deep` to analyze management sentiment (Are they buying or selling?). Classify as accumulation, distribution, or neutral.
4. **Growth Assessment:** Analyze revenue growth trajectory, cash flow stability, and corporate guidance found in SEC reports.
5. **Risk Flagging:** Identify red flags (declining margins, rising debt, negative free cash flow, going concern warnings).
6. **Value Synthesis:** Summarize the company's overall fundamental strength. For each finding, state: direction (positive/negative/neutral), magnitude (strong/moderate/weak), and confidence.

### Guidelines:
- Use `get_fundamentals` for a broad overview.
- Use `get_sec_filings` to find 10-K/10-Q reports for management discussion and analysis (MD&A).
- Prioritize high-volume insider buying as a strong positive signal.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Fundamental analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical fundamental and regulatory findings, each with confidence level.
2. **Financial Health Dashboard:** Key ratios compared to sector averages, profit margins trend, and efficiency metrics.
3. **Growth & Cash Flow Analysis:** Revenue trajectory, free cash flow stability, and earnings quality assessment.
4. **SEC & Insider Sentiment:** Specific breakdown of recent filings and insider trading activity with classification.
5. **Risk Flags:** Explicit list of red flags or concerns identified, if any.
6. **Financial Data Table:** A Markdown table summarizing key fundamental metrics, current values, sector comparison, and signal."""

        ticker = state.get("company_of_interest", "")

        trade_date = state.get("trade_date", "")

        try:
            fund_data = await route_to_vendor("get_fundamentals", ticker, trade_date)

        except Exception:
            fund_data = ""

        try:
            bs_data = await route_to_vendor("get_balance_sheet", ticker, "quarterly", trade_date)

        except Exception:
            bs_data = ""

        try:
            cf_data = await route_to_vendor("get_cashflow", ticker, "quarterly", trade_date)

        except Exception:
            cf_data = ""

        try:
            is_data = await route_to_vendor("get_income_statement", ticker, "quarterly", trade_date)

        except Exception:
            is_data = ""

        try:
            sec_data = await route_to_vendor("get_sec_filings", ticker)

        except Exception:
            sec_data = ""

        try:
            insider_data = await route_to_vendor("get_insider_transactions", ticker)

        except Exception:
            insider_data = ""

        data_hash = compute_data_hash(
            "fundamentals", ticker, trade_date, fund_data, bs_data, cf_data, is_data, sec_data, insider_data
        )

        cached_report = await check_analyst_cache("fundamentals", ticker, data_hash)

        if cached_report:
            await emit_cache_hit("fundamentals", ticker)

            return {
                "messages": [AIMessage(content=cached_report)],
                "fundamentals_report": cached_report,
            }

        res = await run_tool_analyst(
            llm,
            state,
            tools=tools,
            system_message=system_message,
            report_key="fundamentals_report",
            instrument_context=instrument_context,
        )

        report_text = res.get("fundamentals_report", "")

        if report_text and not report_text.startswith("Fundamentals analysis unavailable"):
            await store_analyst_cache("fundamentals", ticker, data_hash, report_text)

        return res

    return fundamentals_analyst_node
