import logging
from datetime import UTC, datetime

import yfinance as yf
from dateutil.relativedelta import relativedelta

from .config import get_config
from .stockstats_utils import yf_retry

_logger = logging.getLogger(__name__)

_NO_TITLE = "No title"

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

def _to_utc(dt: datetime | None) -> datetime | None:
    """Normalize a parsed publish datetime to aware UTC.

    _parse_news_datetime returns a mix of aware (timestamps / ISO with offset)
    and naive (ISO without offset) datetimes. Comparing those against date
    boundaries inconsistently (the old code stripped tz and compared a UTC
    wall-clock against naive local dates) skewed which articles fell inside the
    window. Treat naive values as UTC and convert aware values to UTC so both
    sides of the comparison share one timezone.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

def _extract_article_data(article: dict) -> dict:
    if "content" in article:
        content = article["content"]
        title = content.get("title", _NO_TITLE)
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
            "title": article.get("title", _NO_TITLE),
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

        cached_items = await get_news_feed(ticker, article_limit)
        cached_items = cached_items or []

        start_boundary = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_boundary = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC) + relativedelta(days=1)
        news_str = ""
        filtered_count = 0

        for item in cached_items:
            item_ticker = (item.get("ticker") or "").upper()
            if item_ticker and item_ticker != ticker.upper():
                continue
            pub_date = _to_utc(_parse_news_datetime(item.get("published_at")))
            # Unknown publication timestamps cannot be proven to have existed
            # inside the requested point-in-time window. Fail closed.
            if pub_date is None or not (start_boundary <= pub_date < end_boundary):
                continue
            title = item.get("title") or _NO_TITLE
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
        _logger.exception("Unexpected error fetching news for %s", ticker)
        return f"Error fetching news for {ticker}: {str(e)}"

def get_global_news_yfinance(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
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
        start_boundary = start_dt.replace(tzinfo=UTC)
        end_boundary = curr_dt.replace(tzinfo=UTC) + relativedelta(days=1)
        news_str = ""
        for article in all_news[:limit]:
            if "content" in article:
                data = _extract_article_data(article)
                pub_utc = _to_utc(data.get("pub_date"))
                if pub_utc is None or not (start_boundary <= pub_utc < end_boundary):
                    continue
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                # Legacy Yahoo result shapes do not expose a reliable
                # publication timestamp and are unsafe for dated analysis.
                continue
            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
    except Exception as e:
        _logger.exception("Unexpected error fetching global news")
        return f"Error fetching global news: {str(e)}"
