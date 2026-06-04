from datetime import datetime, timedelta
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.agents.analyst_registry import register_analyst
def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
@register_analyst(
    key="social",
    agent_node="Sentiment Analyst",
    clear_node="Msg Clear Sentiment",
    tool_node="tools_social",
    report_key="sentiment_report",
    tools=[],
)
def create_sentiment_analyst(llm):
    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)
        news_block = get_news.func(ticker, start_date, end_date)
        stocktwits_block = fetch_stocktwits_messages(ticker, limit=30)
        reddit_block = fetch_reddit_posts(ticker)
        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            stocktwits_block=stocktwits_block,
            reddit_block=reddit_block,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        chain = prompt | llm
        result = chain.invoke(state["messages"])
        return {
            "messages": [result],
            "sentiment_report": result.content,
        }
    return sentiment_analyst_node
def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return f"""You are a senior financial sentiment analyst. Your task is to produce a high-conviction sentiment report for {ticker} by synthesizing retail and institutional data.

### Analytical Process (Chain-of-Thought):
1. **Source Evaluation:** Review pre-fetched data from News, StockTwits, and Reddit.
2. **Signal Weighting:** Weight institutional news vs. fast-moving retail social signals.
3. **Conflict Detection:** Identify divergences between sources (e.g., bearish news vs. bullish retail).
4. **Narrative Synthesis:** Formulate the dominant market sentiment narrative.

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
2. **Cross-Source Divergence:** Mismatches between news and retail often signal early trend shifts.
3. **Engagement Weighting:** Prioritize high-upvote Reddit posts over low-engagement noise.
4. **Narrative Identification:** Pinpoint recurring themes driving the current sentiment.
5. **Data Quality:** Flag explicitly if sample sizes are low or data is unavailable.

## Output Format
Your final report MUST follow this structure:
1. **Executive Summary:** A 3-bullet point summary of the overall sentiment direction and confidence.
2. **Detailed Analysis:** Nuanced breakdown of each source, cross-source alignments/divergences, and key narratives.
3. **Catalysts and Risks:** Specific upcoming events or sentiment-driven risks identified.
4. **Sentiment Data Table:** A Markdown table summarizing key signals, their direction, source, and evidence.
{get_language_instruction()}"""
def create_social_media_analyst(llm):
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
