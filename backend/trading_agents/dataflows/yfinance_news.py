import logging
from datetime import UTC, datetime

import yfinance as yf
from dateutil.relativedelta import relativedelta

from .config import get_config
from .stockstats_utils import yf_retry

_logger = logging.getLogger(__name__)


def _parse_news_datetime(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw_value), tz=UTC)
        except Exception:
            return None
    if isinstance(raw_value, str):
        raw = raw_value.strip()
        if not raw:
            return None
        if raw.isdigit():
            try:
                return datetime.fromtimestamp(float(raw), tz=UTC)
            except Exception:
                return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _extract_article_data(article: dict) -> dict:
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")
        pub_date = _parse_news_datetime(content.get("pubDate"))
        if pub_date is None:
            pub_date = _parse_news_datetime(article.get("providerPublishTime"))
        return {
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "link": link,
            "pub_date": pub_date,
        }
    else:
        return {
            "title": article.get("title", "No title"),
            "summary": article.get("summary", ""),
            "publisher": article.get("publisher", "Unknown"),
            "link": article.get("link", ""),
            "pub_date": None,
        }


async def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    article_limit = get_config()["news_article_limit"]
    try:
        from backend.services.news_service import get_news_feed

        # Correctly await the async news feed service in the main loop
        cached_items = await get_news_feed(ticker, article_limit)
        cached_items = cached_items or []

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        news_str = ""
        filtered_count = 0

        for item in cached_items:
            item_ticker = (item.get("ticker") or "").upper()
            if item_ticker and item_ticker != ticker.upper():
                continue
            pub_date = _parse_news_datetime(item.get("published_at"))
            if pub_date:
                pub_date_naive = pub_date.replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue
            title = item.get("title") or "No title"
            summary = item.get("summary") or ""
            publisher = item.get("source") or "Unknown"
            link = item.get("url") or ""
            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            filtered_count += 1

        if filtered_count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"
        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"
    except Exception as e:
        _logger.error("Unexpected error fetching news for %s: %s", ticker, e, exc_info=True)
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    # yfinance.Search is sync, so it will be wrapped by route_to_vendor's to_thread
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]
    search_queries = config["global_news_queries"]
    all_news = []
    seen_titles = set()
    try:
        for query in search_queries:
            search = yf_retry(
                lambda q=query: yf.Search(
                    query=q,
                    news_count=limit,
                    enable_fuzzy_query=True,
                )
            )
            if search.news:
                for article in search.news:
                    if "content" in article:
                        data = _extract_article_data(article)
                        title = data["title"]
                    else:
                        title = article.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)
            if len(all_news) >= limit:
                break
        if not all_news:
            return f"No global news found for {curr_date}"
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")
        news_str = ""
        for article in all_news[:limit]:
            if "content" in article:
                data = _extract_article_data(article)
                if data.get("pub_date"):
                    pub_naive = (
                        data["pub_date"].replace(tzinfo=None)
                        if hasattr(data["pub_date"], "replace")
                        else data["pub_date"]
                    )
                    if pub_naive > curr_dt + relativedelta(days=1):
                        continue
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")
                summary = ""
            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
    except Exception as e:
        _logger.error("Unexpected error fetching global news: %s", e, exc_info=True)
        return f"Error fetching global news: {str(e)}"
