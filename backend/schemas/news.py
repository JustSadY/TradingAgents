"""Response contract for the dashboard news feed."""

from pydantic import BaseModel


class NewsItem(BaseModel):
    """One headline, normalised across the shapes the vendor returns.

    `news_service` writes exactly these keys into the cache table, so cached
    and freshly fetched items validate against the same model.
    """

    ticker: str
    title: str
    summary: str
    url: str
    published_at: str
    source: str
