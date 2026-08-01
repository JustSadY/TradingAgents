from datetime import datetime, timedelta

from langchain_core.messages import AIMessage

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.search_tools import get_crypto_fear_and_greed_index
from backend.trading_agents.agents.runtime.analyst_cache import (
    check_analyst_cache,
    compute_data_hash,
    emit_cache_hit,
    store_analyst_cache,
)
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_system_instruction_override,
)
from backend.trading_agents.dataflows.interface import fetch_reddit_posts, fetch_stocktwits_messages, route_to_vendor


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


@register_analyst(
    key="social",
    agent_node="Sentiment Analyst",
    clear_node="Msg Clear Sentiment",
    tool_node="tools_social",
    report_key="sentiment_report",
    tools=[get_crypto_fear_and_greed_index],
)
def create_sentiment_analyst(llm):
    async def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        reddit_enabled = True
        stocktwits_enabled = True
        if ctx and "graph" in ctx:
            graph = ctx["graph"]
            filtered = graph._filter_tools_for_analyst("social", [fetch_reddit_posts, fetch_stocktwits_messages])
            reddit_enabled = fetch_reddit_posts in filtered
            stocktwits_enabled = fetch_stocktwits_messages in filtered

        news_block = await route_to_vendor("get_news", ticker, start_date, end_date)

        from backend.trading_agents.dataflows.config import get_config

        user_tool_settings = get_config().get("runtime_tool_context", {}).get("user_settings", {})
        reddit_limit = int(user_tool_settings.get("reddit_sentiment", {}).get("settings", {}).get("limit", 5) or 5)
        stocktwits_limit = int(
            user_tool_settings.get("stocktwits_sentiment", {}).get("settings", {}).get("limit", 30) or 30
        )

        if reddit_enabled:
            reddit_block = await route_to_vendor("fetch_reddit_posts", ticker, limit_per_sub=reddit_limit)
        else:
            reddit_block = "Reddit sentiment data source is disabled by user or server settings."

        if stocktwits_enabled:
            stocktwits_block = await route_to_vendor("fetch_stocktwits_messages", ticker, limit=stocktwits_limit)
        else:
            stocktwits_block = "StockTwits sentiment data source is disabled by user or server settings."

        data_hash = compute_data_hash("social", ticker, end_date, news_block, reddit_block, stocktwits_block)
        cached_report = await check_analyst_cache("social", ticker, data_hash)
        if cached_report:
            await emit_cache_hit("social", ticker)
            return {
                "messages": [AIMessage(content=cached_report)],
                "sentiment_report": cached_report,
            }

        override = get_system_instruction_override("social")
        if override:
            system_message = override
        else:
            system_message = _build_system_message(
                ticker=ticker,
                news_block=news_block,
                stocktwits_block=stocktwits_block,
                reddit_block=reddit_block,
            )
        # Keep the pre-fetched social sources, but route the final LLM turn through
        # the same report boundary as every other analyst.  Some providers can
        # return ``None``/content blocks/whitespace after a successful request;
        # the shared runner normalizes that and makes one bounded text-only
        # recovery attempt instead of persisting an empty Sentiment panel.
        result = await run_tool_analyst(
            llm,
            state,
            tools=[],
            system_message=system_message,
            report_key="sentiment_report",
            instrument_context=instrument_context,
        )
        report_text = result.get("sentiment_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("social", ticker, data_hash, report_text)
        return result

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return f"""You are a senior financial sentiment analyst. Your role is EXCLUSIVELY sentiment measurement — you do NOT make buy/sell/hold recommendations. Output only sentiment observations.

### Analytical Process (Chain-of-Thought):
1. **Source Evaluation:** Review pre-fetched data from News, StockTwits, and Reddit. Note sample sizes for each source.
2. **Quantitative Scoring:** For each source, estimate a sentiment score (-1.0 to +1.0) and volume of signal (high/medium/low).
3. **Signal Weighting:** Weight institutional news vs. fast-moving retail social signals based on timeliness and credibility.
4. **Conflict Detection:** Identify divergences between sources (e.g., bearish news vs. bullish retail) — mismatches are often early trend shift indicators.
5. **Narrative Synthesis:** Pinpoint the dominant sentiment narrative and assign a conviction level.

## Data sources (pre-fetched)
### News headlines — Yahoo Finance
Institutional framing. Fact-driven, slower-moving signal.
<start_of_news>
{news_block}
<end_of_news>
### StockTwits messages
Fast-moving retail signal. Each message carries a user-labeled sentiment tag.
<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>
### Reddit posts — r/wallstreetbets, r/stocks, r/investing
Community discussion. Engagement signal via upvote score and comment count.
<start_of_reddit>
{reddit_block}
<end_of_reddit>

## Analysis Guidelines
1. **StockTwits Ratios:** Read Bullish/Bearish ratios as leading signals. ≥90/10 may indicate over-extension (contrarian risk).
2. **Cross-Source Divergence:** Mismatches between news and retail often signal early trend shifts — note direction of divergence.
3. **Engagement Weighting:** Prioritize high-upvote Reddit posts over low-engagement noise.
4. **Narrative Identification:** Pinpoint recurring themes driving the current sentiment.
5. **Data Quality:** Flag explicitly if sample sizes are low or data is unavailable.
6. **IMPORTANT:** NEVER output a Buy/Sell/Hold rating. Sentiment measurement only.
7. **IMPORTANT:** State a quantitative sentiment score (-1.0 to +1.0) per source and an aggregate overall score.

## Output Format
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the overall sentiment direction, aggregate score, and conviction level.
2. **Detailed Analysis:** Nuanced breakdown of each source with quantitative scores, cross-source alignments/divergences, and key narratives.
3. **Catalysts and Risks:** Specific upcoming events or sentiment-driven risks identified.
4. **Sentiment Data Table:** A Markdown table summarizing key signals, their direction, source, quantitative score, and evidence.
"""
