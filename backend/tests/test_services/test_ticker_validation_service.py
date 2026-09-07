from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.services import ticker_validation_service as ticker_validation


@pytest.fixture(autouse=True)
def _clear_validation_cache():
    ticker_validation._VALID_CACHE.clear()
    ticker_validation._INVALID_CACHE.clear()
    yield
    ticker_validation._VALID_CACHE.clear()
    ticker_validation._INVALID_CACHE.clear()


async def test_valid_ticker_is_confirmed_from_exact_quote_match(monkeypatch):
    quote_lookup = AsyncMock(return_value=[{"symbol": "AAPL", "quoteType": "EQUITY"}])
    search_lookup = AsyncMock()
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", quote_lookup)
    monkeypatch.setattr(ticker_validation, "_fetch_search_candidates", search_lookup)

    result = await ticker_validation.validate_analysis_ticker(" aapl ")

    assert result.ticker == "AAPL"
    assert quote_lookup.await_count == 1
    assert quote_lookup.await_args.args[0] == "AAPL"
    assert quote_lookup.await_args.args[1] is not None
    search_lookup.assert_not_awaited()


async def test_unknown_ticker_returns_suggestions_without_substitution(monkeypatch):
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        ticker_validation,
        "_fetch_search_candidates",
        AsyncMock(
            return_value=[
                {"symbol": "NVDA", "shortname": "NVIDIA Corporation", "quoteType": "EQUITY"},
                {"symbol": "NVDL", "shortname": "GraniteShares 2x Long NVDA", "quoteType": "ETF"},
            ]
        ),
    )

    with pytest.raises(ticker_validation.TickerNotFoundError) as exc_info:
        await ticker_validation.validate_analysis_ticker("nvdia")

    error = exc_info.value
    assert error.ticker == "NVDIA"
    assert [suggestion.symbol for suggestion in error.suggestions] == ["NVDA", "NVDL"]


async def test_transient_lookup_failure_is_not_reported_as_unknown_ticker(monkeypatch):
    async def unavailable(_: str, _client=None):
        raise ticker_validation.TickerValidationUnavailableError("upstream timeout")

    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", unavailable)
    monkeypatch.setattr(ticker_validation, "_fetch_search_candidates", unavailable)

    with pytest.raises(ticker_validation.TickerValidationUnavailableError):
        await ticker_validation.validate_analysis_ticker("AAPL")


async def test_search_can_confirm_symbol_when_quote_endpoint_is_temporarily_blocked(monkeypatch):
    async def quote_unavailable(_: str, _client=None):
        raise ticker_validation.TickerValidationUnavailableError("quote endpoint blocked")

    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", quote_unavailable)
    monkeypatch.setattr(
        ticker_validation,
        "_fetch_search_candidates",
        AsyncMock(return_value=[{"symbol": "AAPL", "shortname": "Apple Inc.", "quoteType": "EQUITY"}]),
    )

    result = await ticker_validation.validate_analysis_ticker("AAPL")

    assert result.ticker == "AAPL"


async def test_portfolio_syntax_failure_makes_no_remote_requests(monkeypatch):
    quote_lookup = AsyncMock()
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", quote_lookup)

    with pytest.raises(ValueError, match="invalid characters"):
        await ticker_validation.validate_analysis_tickers(["AAPL", "../BAD"])

    quote_lookup.assert_not_awaited()


async def test_portfolio_validation_deduplicates_normalized_tickers(monkeypatch):
    async def quote_lookup(ticker: str, _client=None):
        return [{"symbol": ticker, "quoteType": "EQUITY"}]

    lookup = AsyncMock(side_effect=quote_lookup)
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", lookup)
    monkeypatch.setattr(ticker_validation, "_fetch_search_candidates", AsyncMock())

    results = await ticker_validation.validate_analysis_tickers([" aapl ", "AAPL", "msft", "MSFT"])

    assert [result.ticker for result in results] == ["AAPL", "MSFT"]
    assert lookup.await_count == 2
    assert {call.args[0] for call in lookup.await_args_list} == {"AAPL", "MSFT"}


async def test_portfolio_validation_reuses_one_http_client(monkeypatch):
    created_clients: list[object] = []
    lookup_clients: list[object] = []

    class _ClientContext:
        def __init__(self, **_kwargs) -> None:
            self.client = object()

        async def __aenter__(self):
            created_clients.append(self.client)
            return self.client

        async def __aexit__(self, *_args) -> bool:
            return False

    async def quote_lookup(ticker: str, client=None):
        lookup_clients.append(client)
        return [{"symbol": ticker, "quoteType": "EQUITY"}]

    monkeypatch.setattr(ticker_validation.httpx, "AsyncClient", _ClientContext)
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", quote_lookup)
    monkeypatch.setattr(ticker_validation, "_fetch_search_candidates", AsyncMock())

    results = await ticker_validation.validate_analysis_tickers(["AAPL", "MSFT", "NVDA"])

    assert [result.ticker for result in results] == ["AAPL", "MSFT", "NVDA"]
    assert len(created_clients) == 1
    assert lookup_clients == [created_clients[0], created_clients[0], created_clients[0]]


async def test_cached_ticker_validation_opens_no_http_client(monkeypatch):
    ticker_validation._VALID_CACHE["AAPL"] = True

    class _ShouldNotOpen:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("cache hit must not construct an HTTP client")

    monkeypatch.setattr(ticker_validation.httpx, "AsyncClient", _ShouldNotOpen)

    result = await ticker_validation.validate_analysis_ticker("AAPL")

    assert result.ticker == "AAPL"


async def test_portfolio_requires_two_distinct_tickers_before_remote_lookup(monkeypatch):
    quote_lookup = AsyncMock()
    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", quote_lookup)

    with pytest.raises(ValueError, match="at least 2 distinct tickers"):
        await ticker_validation.validate_analysis_tickers(["AAPL", " aapl "])

    quote_lookup.assert_not_awaited()
