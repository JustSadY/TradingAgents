import logging
from typing import Optional
import yfinance as yf
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .config import get_config
from .stockstats_utils import yf_retry
_logger = logging.getLogger(__name__)
def _extract_article_data(article: dict) -> dict:
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
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
def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    article_limit = get_config()["news_article_limit"]
    try:
        stock = yf.Ticker(ticker)
        news = yf_retry(lambda: stock.get_news(count=article_limit))
        if not news:
            return f"No news found for {ticker}"
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        news_str = ""
        filtered_count = 0
        for article in news:
            data = _extract_article_data(article)
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue
            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
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
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
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
            search = yf_retry(lambda q=query: yf.Search(
                query=q,
                news_count=limit,
                enable_fuzzy_query=True,
            ))
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
                    pub_naive = data["pub_date"].replace(tzinfo=None) if hasattr(data["pub_date"], "replace") else data["pub_date"]
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
