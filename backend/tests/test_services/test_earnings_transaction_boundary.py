from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.services import earnings_service, settings_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_watchlist_earnings_release_db_before_provider_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_settings(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(watchlist=["AAPL"])

    def fake_fetch(ticker: str) -> earnings_service.EarningsEntry:
        assert ticker == "AAPL"
        assert db.commits == 1
        return earnings_service.EarningsEntry(
            ticker=ticker,
            earnings_date=None,
            eps_estimate=None,
            reported_eps=None,
            surprise_pct=None,
            days_until=None,
            status="unknown",
        )

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(earnings_service, "fetch_earnings", fake_fetch)

    result = await earnings_service.get_earnings_calendar(db, user=object(), tickers=None)

    assert result[0]["ticker"] == "AAPL"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_explicit_earnings_tickers_do_not_commit_caller_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    def fake_fetch(ticker: str) -> earnings_service.EarningsEntry:
        assert db.commits == 0
        return earnings_service.EarningsEntry(
            ticker=ticker,
            earnings_date=None,
            eps_estimate=None,
            reported_eps=None,
            surprise_pct=None,
            days_until=None,
            status="unknown",
        )

    monkeypatch.setattr(earnings_service, "fetch_earnings", fake_fetch)

    result = await earnings_service.get_earnings_calendar(db, user=object(), tickers="AAPL")

    assert result[0]["ticker"] == "AAPL"
    assert db.commits == 0
