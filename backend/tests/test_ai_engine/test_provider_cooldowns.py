"""Regression coverage for noisy market-data provider failures."""

from __future__ import annotations

import logging
from urllib.error import HTTPError

import pandas as pd
import pytest
from yfinance.exceptions import YFPricesMissingError, YFTzMissingError

from backend.trading_agents.dataflows import config as dataflow_config
from backend.trading_agents.dataflows.cache import APICache
from backend.trading_agents.dataflows.config import set_config
from backend.trading_agents.dataflows.stockstats_utils import (
    YFinanceTickerUnavailableError,
    reset_yfinance_ticker_cooldowns,
    yf_retry,
)
from backend.trading_agents.dataflows.stocktwits import (
    StockTwitsUnavailable,
    fetch_stocktwits_messages,
    reset_stocktwits_cooldown,
)


@pytest.fixture(autouse=True)
def _reset_provider_state(tmp_path):
    old_get_path = APICache.get_cache_path
    APICache.get_cache_path = staticmethod(lambda: tmp_path / "test_api_cache.sqlite3")
    APICache._initialized_paths.discard(str(tmp_path / "test_api_cache.sqlite3"))
    dataflow_config._config = None
    dataflow_config.initialize_config()
    reset_yfinance_ticker_cooldowns()
    reset_stocktwits_cooldown()
    yield
    reset_yfinance_ticker_cooldowns()
    reset_stocktwits_cooldown()
    APICache.get_cache_path = old_get_path
    APICache._initialized_paths.clear()

def _http_error(code: int) -> HTTPError:
    return HTTPError("https://api.stocktwits.com/test", code, "test error", hdrs=None, fp=None)

def test_stocktwits_403_is_logged_once_then_cooldown_skips_network(monkeypatch, caplog):
    import backend.trading_agents.dataflows.stocktwits as stocktwits

    calls = 0

    def denied(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise _http_error(403)

    monkeypatch.setattr(stocktwits, "urlopen", denied)
    caplog.set_level(logging.DEBUG, logger=stocktwits.__name__)

    first = fetch_stocktwits_messages("AAPL")
    second = fetch_stocktwits_messages("AAPL")

    assert "HTTP 403 access denied" in first
    assert "HTTP 403 access denied" in second
    assert isinstance(first, StockTwitsUnavailable)
    assert isinstance(second, StockTwitsUnavailable)
    assert calls == 1
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1

def test_yfinance_missing_ticker_is_cooled_down_without_reinvoking_provider():
    calls = 0

    def missing():
        nonlocal calls
        calls += 1
        raise YFTzMissingError("NOTAREALTICKER")

    with pytest.raises(YFinanceTickerUnavailableError) as first:
        yf_retry(missing, max_retries=0, ticker="notarealticker")

    assert first.value.from_cooldown is False
    assert calls == 1

    with pytest.raises(YFinanceTickerUnavailableError) as cached:
        yf_retry(lambda: pytest.fail("Yahoo must not be reinvoked during cooldown"), ticker="NOTAREALTICKER")

    assert cached.value.from_cooldown is True
    assert calls == 1

def test_yfinance_price_range_gap_does_not_poison_ticker_cooldown():
    with pytest.raises(YFPricesMissingError):
        yf_retry(
            lambda: (_ for _ in ()).throw(YFPricesMissingError("NEWIPO", "for period 2010-01-01")),
            max_retries=0,
            ticker="NEWIPO",
        )

    assert yf_retry(lambda: "available now", ticker="NEWIPO") == "available now"

def test_load_ohlcv_uses_single_ticker_history_with_typed_errors(monkeypatch):
    import backend.trading_agents.dataflows.stockstats_utils as stockstats_utils

    calls: list[tuple[str, dict]] = []
    index = pd.DatetimeIndex(["2024-01-08", "2024-01-09"], name="Date")
    history = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1200],
        },
        index=index,
    )

    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append((self.symbol, kwargs))
            return history

    monkeypatch.setattr(stockstats_utils.yf, "Ticker", _Ticker)

    data = stockstats_utils.load_ohlcv("aapl", "2024-01-10")

    assert list(data["Close"]) == [101.0, 102.0]
    assert calls == [
        (
            "AAPL",
            {
                "start": "2019-01-10",
                "end": "2024-01-11",
                "auto_adjust": True,
                "actions": False,
                "raise_errors": True,
            },
        )
    ]

def test_load_ohlcv_normalizes_exchange_timezone_before_date_filter(monkeypatch):
    """Fresh Yahoo history must compare safely with a date-only trade date."""
    import backend.trading_agents.dataflows.stockstats_utils as stockstats_utils

    index = pd.DatetimeIndex(
        ["2024-01-08", "2024-01-09"],
        tz="America/New_York",
        name="Date",
    )
    history = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1200],
        },
        index=index,
    )

    class _Ticker:
        def __init__(self, _symbol: str):
            pass

        def history(self, **_kwargs):
            return history

    monkeypatch.setattr(stockstats_utils.yf, "Ticker", _Ticker)

    data = stockstats_utils.load_ohlcv("AAPL", "2024-01-10")

    assert data["Date"].dt.tz is None
    assert data["Date"].max() == pd.Timestamp("2024-01-09")

def test_direct_yfinance_stock_data_uses_typed_history_errors(monkeypatch):
    import backend.trading_agents.dataflows.y_finance as y_finance

    calls: list[tuple[str, dict]] = []
    index = pd.DatetimeIndex(["2024-01-08", "2024-01-09"], name="Date")
    history = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1200],
        },
        index=index,
    )

    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append((self.symbol, kwargs))
            return history

    monkeypatch.setattr(y_finance.yf, "Ticker", _Ticker)

    result = y_finance.get_yfin_data_online("aapl", "2024-01-01", "2024-01-10")

    assert "# Stock data for AAPL" in result
    assert "2024-01-08" in result
    # `end_date` is inclusive for callers — the trade date's own bar has to be
    # in the result, and start == end has to return that one day. Yahoo's `end`
    # is exclusive, so the request carries the day after.
    assert calls == [
        (
            "AAPL",
            {
                "start": "2024-01-01",
                "end": "2024-01-11",
                "raise_errors": True,
            },
        )
    ]


def test_direct_yfinance_stock_data_keeps_the_end_date_bar_and_nothing_later(monkeypatch):
    import backend.trading_agents.dataflows.y_finance as y_finance

    # The widened request can return the following session too; only the
    # inclusive window may reach the caller.
    index = pd.DatetimeIndex(["2024-01-10", "2024-01-11"], name="Date")
    history = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1200],
        },
        index=index,
    )

    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, **_kwargs):
            return history

    monkeypatch.setattr(y_finance.yf, "Ticker", _Ticker)

    single_day = y_finance.get_yfin_data_online("AAPL", "2024-01-10", "2024-01-10")

    assert "2024-01-10" in single_day
    assert "2024-01-11" not in single_day

@pytest.mark.asyncio
async def test_unavailable_yfinance_ticker_falls_through_to_next_vendor():
    from backend.trading_agents.dataflows.interface import VENDOR_METHODS, route_to_vendor

    set_config({"tool_vendors": {"get_stock_data": "yfinance,alpha_vantage"}})
    original = VENDOR_METHODS["get_stock_data"]
    yfinance_calls = 0
    alternate_calls = 0

    async def yfinance(*_args, **_kwargs):
        nonlocal yfinance_calls
        yfinance_calls += 1
        raise YFinanceTickerUnavailableError("NOTAREALTICKER", "no timezone found", 300, from_cooldown=True)

    async def alternate(*_args, **_kwargs):
        nonlocal alternate_calls
        alternate_calls += 1
        return "alternate vendor data"

    VENDOR_METHODS["get_stock_data"] = {"yfinance": yfinance, "alpha_vantage": alternate}
    try:
        result = await route_to_vendor("get_stock_data", "NOTAREALTICKER", "2024-01-01", "2024-01-31")
    finally:
        VENDOR_METHODS["get_stock_data"] = original

    assert result == "alternate vendor data"
    assert yfinance_calls == 1
    assert alternate_calls == 1

@pytest.mark.asyncio
async def test_stocktwits_unavailable_marker_is_not_cached():
    from backend.trading_agents.dataflows.interface import VENDOR_METHODS, route_to_vendor

    original = VENDOR_METHODS["fetch_stocktwits_messages"]
    calls = 0

    async def unavailable(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return StockTwitsUnavailable("<stocktwits unavailable: HTTP 403 access denied>")

    VENDOR_METHODS["fetch_stocktwits_messages"] = {"stocktwits": unavailable}
    try:
        first = await route_to_vendor("fetch_stocktwits_messages", "AAPL")
        second = await route_to_vendor("fetch_stocktwits_messages", "AAPL")
    finally:
        VENDOR_METHODS["fetch_stocktwits_messages"] = original

    assert isinstance(first, StockTwitsUnavailable)
    assert isinstance(second, StockTwitsUnavailable)
    assert calls == 2
