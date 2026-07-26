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

        from datetime import datetime, timedelta

        from langchain_core.messages import AIMessage

        from backend.trading_agents.agents.runtime.analyst_cache import (
            check_analyst_cache,
            compute_data_hash,
            emit_cache_hit,
            store_analyst_cache,
        )
        from backend.trading_agents.dataflows.interface import route_to_vendor

        asset_type = state.get("asset_type", "stock")

        asset_label = "company" if asset_type == "stock" else "asset"

        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)

        tools = _NEWS_TOOLS

        system_message = f"""You are a senior news analyst. Your role is EXCLUSIVELY news interpretation — you do NOT make buy/sell/hold recommendations. Output only event-driven observations.

### Analytical Process (Chain-of-Thought):
1. **Targeted Search:** Use `get_news` to find stories specific to the {asset_label} of interest.
2. **Global Context:** Use `get_global_news` to capture macroeconomic trends and geopolitical events.
3. **Corroborating Signals:** For stocks, use `get_insider_transactions` to check for notable insider buying/selling. For crypto assets, use `get_crypto_fear_and_greed_index` to gauge market sentiment.
4. **Event Impact Analysis:** For each event, classify: type, expected impact magnitude (HIGH/MEDIUM/LOW), direction (positive/negative/neutral), and confidence.
5. **Narrative Synthesis:** Determine the prevailing narrative shift based on the latest headlines and assign a confidence level.

### Guidelines:
- Focus on the past week of data.
- Distinguish between "noise" and high-impact "catalysts" with explicit reasoning.
- Provide evidence-based insights with citations where possible.
- **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. News analysis only.
- Assign a confidence level (HIGH/MEDIUM/LOW) to each key observation.

### Output Format:
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the most critical news catalysts and their estimated impact.
2. **Detailed Analysis:** Comprehensive review of {asset_label}-specific and global macroeconomic developments, each with direction, impact, and confidence.
3. **Insider Activity Note:** Summary of any notable insider transactions found, with trend (accumulation/distribution).
4. **Upcoming Catalysts:** Specific upcoming catalysts or risks for traders to monitor with dates.
5. **News Event Table:** A Markdown table summarizing key events, their dates, impact (High/Med/Low), confidence, and a brief description."""

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
            try:
                import asyncio

                from backend.trading_agents.dataflows.crypto_fear_greed import (
                    fetch_crypto_fear_greed_index,
                )

                crypto_data = await asyncio.to_thread(fetch_crypto_fear_greed_index)

            except Exception:
                crypto_data = ""

        articles_hash = compute_data_hash(
            "news", ticker, trade_date, news_data, global_news_data, insider_data, crypto_data
        )

        cached_report = await check_analyst_cache("news", ticker, articles_hash)

        if cached_report:
            await emit_cache_hit("news", ticker)

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

        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("news", ticker, articles_hash, report_text)

        return res

    return news_analyst_node
