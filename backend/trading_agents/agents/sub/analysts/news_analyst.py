from backend.trading_agents.agents.analyst_registry import register_analyst

from backend.trading_agents.agents.data.search_tools import get_crypto_fear_and_greed_index

from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst

from backend.trading_agents.agents.utils.agent_utils import (

    build_instrument_context,

    get_global_news,

    get_insider_transactions,

    get_news,

)



                                                                               

                                                                               

                                                                            

         

_NEWS_TOOLS = [get_news, get_global_news, get_insider_transactions, get_crypto_fear_and_greed_index]





@register_analyst(

    key="news",

    agent_node="News Analyst",

    clear_node="Msg Clear News",

    tool_node="tools_news",

    report_key="news_report",

    tools=_NEWS_TOOLS,

)

def create_news_analyst(llm):

    async def news_analyst_node(state):

        import hashlib

        from datetime import datetime, timedelta

        from langchain_core.messages import AIMessage

        from sqlalchemy import select

        from backend.core.database import AsyncSessionLocal

        from backend.models.news_cache import NewsAnalysisCache

        from backend.trading_agents.dataflows.interface import route_to_vendor



        asset_type = state.get("asset_type", "stock")

        asset_label = "company" if asset_type == "stock" else "asset"

        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)



        tools = _NEWS_TOOLS



        system_message = f"""You are a senior news and macro analyst. Your goal is to identify market-moving events and broader economic trends through rigorous news analysis.

### Analytical Process (Chain-of-Thought):
1. **Targeted Search:** Use `get_news` to find stories specific to the {asset_label} of interest.
2. **Global Context:** Use `get_global_news` to capture macroeconomic trends and geopolitical events.
3. **Corroborating Signals:** For stocks, use `get_insider_transactions` to check for notable insider buying/selling. For crypto assets, use `get_crypto_fear_and_greed_index` to gauge market sentiment.
4. **Event Impact Analysis:** Evaluate how recent news (Earnings, Mergers, Policy changes) will affect price action.
5. **Sentiment Synthesis:** Determine the prevailing narrative shift based on the latest headlines.

### Guidelines:
- Focus on the past week of data.
- Distinguish between "noise" and high-impact "catalysts."
- Provide evidence-based insights with citations where possible.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical news catalysts.
2. **Detailed Analysis:** Comprehensive review of {asset_label}-specific and global macroeconomic developments.
3. **Actionable Insights:** Specific upcoming catalysts or risks for traders to monitor.
4. **News Event Table:** A Markdown table summarizing key events, their dates, impact (High/Med/Low), and a brief description."""



        ticker = state.get("company_of_interest", "")

        trade_date = state.get("trade_date", "")



        try:

            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")

            start_dt = trade_dt - timedelta(days=7)

            start_date_str = start_dt.strftime("%Y-%m-%d")

        except Exception:

            start_date_str = trade_date



        try:

            news_data = await route_to_vendor("get_news", ticker, start_date_str, trade_date)

        except Exception:

            news_data = ""



        try:

            global_news_data = await route_to_vendor("get_global_news", trade_date)

        except Exception:

            global_news_data = ""



        insider_data = ""

        if asset_type == "stock":

            try:

                insider_data = await route_to_vendor("get_insider_transactions", ticker)

            except Exception:

                insider_data = ""



        crypto_data = ""

        if asset_type == "crypto":

            crypto_data = "Fear and Greed Index: 45 (Neutral)"



        combined_text = f"{ticker}|{trade_date}|{news_data}|{global_news_data}|{insider_data}|{crypto_data}"

        articles_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()



        cached_report = None

        async with AsyncSessionLocal() as db:

            stmt = select(NewsAnalysisCache).where(

                NewsAnalysisCache.ticker == ticker,

                NewsAnalysisCache.articles_hash == articles_hash

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

                await emitter.emit_mental_model("news", f"Reusing cached news analysis for {ticker} (saved tokens).")

            return {

                "messages": [AIMessage(content=cached_report)],

                "news_report": cached_report,

            }



        res = await run_tool_analyst(

            llm,

            state,

            tools=tools,

            system_message=system_message,

            report_key="news_report",

            instrument_context=instrument_context,

        )

        report_text = res.get("news_report", "")

        if report_text and not report_text.startswith("News analysis unavailable"):

            async with AsyncSessionLocal() as db:

                new_entry = NewsAnalysisCache(

                    ticker=ticker,

                    articles_hash=articles_hash,

                    analysis_result=report_text

                )

                db.add(new_entry)

                await db.commit()

        return res



    return news_analyst_node

