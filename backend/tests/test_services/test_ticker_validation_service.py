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
    quote_lookup.assert_awaited_once_with("AAPL")
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
    async def unavailable(_: str):
        raise ticker_validation.TickerValidationUnavailableError("upstream timeout")

    monkeypatch.setattr(ticker_validation, "_fetch_quote_candidates", unavailable)
    monkeypatch.setattr(ticker_validation, "_fetch_search_candidates", unavailable)

    with pytest.raises(ticker_validation.TickerValidationUnavailableError):
        await ticker_validation.validate_analysis_ticker("AAPL")

async def test_search_can_confirm_symbol_when_quote_endpoint_is_temporarily_blocked(monkeypatch):
    async def quote_unavailable(_: str):
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
