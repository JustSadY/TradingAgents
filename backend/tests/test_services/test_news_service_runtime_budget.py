import asyncio

from backend.services import news_service


async def test_news_cache_misses_use_bounded_parallel_fetches(monkeypatch) -> None:
    active = 0
    max_active = 0

    async def fake_to_thread(_fn, ticker):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return [{"title": f"News for {ticker}", "providerPublishTime": "1"}]

    monkeypatch.setattr(news_service.asyncio, "to_thread", fake_to_thread)

    result = await news_service._fetch_news_batch([f"T{index}" for index in range(8)])

    assert len(result) == 8
    assert max_active == news_service._NEWS_FETCH_CONCURRENCY == 4


async def test_news_fetch_releases_db_session_before_external_io(monkeypatch) -> None:
    active_sessions = 0
    opened_sessions = 0
    committed = 0

    class _Scalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        async def __aenter__(self):
            nonlocal active_sessions, opened_sessions
            active_sessions += 1
            opened_sessions += 1
            return self

        async def __aexit__(self, *_args):
            nonlocal active_sessions
            active_sessions -= 1

        async def execute(self, _statement):
            return _Result()

        async def commit(self):
            nonlocal committed
            committed += 1

    async def fake_fetch(tickers):
        assert active_sessions == 0
        return {
            ticker: [
                {
                    "ticker": ticker,
                    "title": f"News for {ticker}",
                    "summary": "",
                    "url": "",
                    "published_at": "1",
                    "source": "",
                }
            ]
            for ticker in tickers
        }

    async def fake_upsert(_db, _ticker, _parsed, _now):
        return None

    monkeypatch.setattr("backend.core.database.AsyncSessionLocal", _Session)
    monkeypatch.setattr(news_service, "_fetch_news_batch", fake_fetch)
    monkeypatch.setattr(news_service, "_upsert_cache", fake_upsert)

    result = await news_service.get_news_feed("AAPL,MSFT", 1)

    assert {item["ticker"] for item in result} == {"AAPL", "MSFT"}
    assert opened_sessions == 2
    assert committed == 1
    assert active_sessions == 0


def test_news_ticker_normalization_dedupes_before_limit() -> None:
    raw = "aapl,AAPL,msft,MSFT," + ",".join(f"T{index}" for index in range(20))

    normalized = news_service._normalize_tickers(raw)

    assert normalized[:2] == ["AAPL", "MSFT"]
    assert len(normalized) == news_service._MAX_TICKERS
    assert len(normalized) == len(set(normalized))
