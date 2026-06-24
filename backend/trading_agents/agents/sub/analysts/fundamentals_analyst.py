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

        import hashlib

        from sqlalchemy import select

        from backend.core.database import AsyncSessionLocal

        from backend.models.news_cache import AnalystReportCache

        from backend.trading_agents.dataflows.interface import route_to_vendor

        from langchain_core.messages import AIMessage



        instrument_context = build_instrument_context(state["company_of_interest"])



        tools = _FUNDAMENTALS_TOOLS



        system_message = """You are a senior fundamental analyst. Your goal is to assess a company's corporate health and intrinsic value through rigorous financial analysis and regulatory monitoring.

### Analytical Process (Chain-of-Thought):
1. **Data Gathering:** Utilize financial statement tools and `get_sec_filings` to retrieve the latest data and regulatory filings.
2. **Financial Health Audit:** Evaluate key ratios (P/E, Debt-to-Equity, Profit Margins) and statement trends.
3. **Insider Intelligence:** Use `get_insider_transactions_deep` to analyze management sentiment (Are they buying or selling?).
4. **Growth Assessment:** Analyze revenue growth, cash flow stability, and corporate guidance found in SEC reports.
5. **Value Synthesis:** Determine the company's overall fundamental strength and value proposition.

### Guidelines:
- Use `get_fundamentals` for a broad overview.
- Use `get_sec_filings` to find 10-K/10-Q reports for management discussion and analysis (MD&A).
- Prioritize high-volume insider buying as a strong bullish signal.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical fundamental and regulatory findings.
2. **Detailed Analysis:** In-depth review of financial statements and corporate history.
3. **SEC & Insider Sentiment:** Specific breakdown of recent filings and insider trading activity.
4. **Actionable Insights:** Specific strengths, weaknesses, or value-driven triggers.
5. **Financial Data Table:** A Markdown table summarizing key fundamental metrics and current values."""



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



        combined_text = f"{ticker}|{trade_date}|{fund_data}|{bs_data}|{cf_data}|{is_data}|{sec_data}|{insider_data}"

        data_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()



        cached_report = None

        async with AsyncSessionLocal() as db:

            stmt = select(AnalystReportCache).where(

                AnalystReportCache.analyst_key == "fundamentals",

                AnalystReportCache.ticker == ticker,

                AnalystReportCache.data_hash == data_hash

            )

            res = await db.execute(stmt)

            entry = res.scalar_one_or_none()

            if entry:

                cached_report = entry.analysis_result



        if cached_report:

            from backend.trading_agents.agents.data.chart_tools import active_run_context

            ctx = active_run_context.get(None)

            if ctx and "emitter" in ctx:

                emitter = ctx["emitter"]

                await emitter.emit_mental_model("fundamentals", f"Reusing cached fundamentals analysis for {ticker} (saved tokens).")

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

            async with AsyncSessionLocal() as db:

                new_entry = AnalystReportCache(

                    analyst_key="fundamentals",

                    ticker=ticker,

                    data_hash=data_hash,

                    analysis_result=report_text

                )

                db.add(new_entry)

                await db.commit()

        return res



    return fundamentals_analyst_node

