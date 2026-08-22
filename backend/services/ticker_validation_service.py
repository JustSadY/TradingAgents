"""Preflight validation for symbols submitted to expensive analysis runs.

The graph fans a ticker out to several market-data providers.  A typo such as
``NVDIA`` used to pass the syntactic path validation, then trigger repeated
yfinance failures after the job had already been queued.  This module performs
a small, bounded Yahoo quote/search lookup at the API boundary instead.

It deliberately returns suggestions rather than substituting a symbol.  A
similarly named instrument can be materially different from the one the user
intended to analyse.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from cachetools import TTLCache

from backend.core.utils import safe_ticker_component

_YAHOO_QUOTE_URL = "https://query2.finance.yahoo.com/v7/finance/quote"
_YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (TradingAgents symbol validation)"}
_REQUEST_TIMEOUT_SECONDS = 3.0
_VALID_CACHE_TTL_SECONDS = 15 * 60
_INVALID_CACHE_TTL_SECONDS = 5 * 60
_MAX_SUGGESTIONS = 3

@dataclass(frozen=True)
class TickerSuggestion:
    """A user-selectable alternative returned by Yahoo's symbol search."""

    symbol: str
    name: str | None = None
    quote_type: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"symbol": self.symbol, "name": self.name, "quote_type": self.quote_type}

@dataclass(frozen=True)
class TickerValidationResult:
    """A confirmed symbol in canonical (upper-case) form."""

    ticker: str

class TickerNotFoundError(ValueError):
    """Raised when the quote provider confirms that a symbol is unknown."""

    def __init__(self, ticker: str, suggestions: tuple[TickerSuggestion, ...] = ()) -> None:
        self.ticker = ticker
        self.suggestions = suggestions
        super().__init__(f"Unknown symbol: {ticker}")

class TickerValidationUnavailableError(RuntimeError):
    """Raised when symbol validation cannot obtain a trustworthy answer."""

_CACHE_MAX_ENTRIES = 2048
# Two stores because the answers keep different company: a symbol that resolved
# is stable, a rejection is worth re-checking sooner.
_VALID_CACHE: TTLCache = TTLCache(maxsize=_CACHE_MAX_ENTRIES, ttl=_VALID_CACHE_TTL_SECONDS)
_INVALID_CACHE: TTLCache = TTLCache(maxsize=_CACHE_MAX_ENTRIES, ttl=_INVALID_CACHE_TTL_SECONDS)

def _normalize_ticker(ticker: str) -> str:
    if not isinstance(ticker, str):
        raise ValueError("Ticker must be a non-empty string.")
    normalized = ticker.strip().upper()
    return safe_ticker_component(normalized)

async def _request_yahoo_json(url: str, *, params: dict[str, str]) -> dict[str, Any] | None:
    """Fetch one Yahoo payload and classify transport failures distinctly."""
    try:
        async with httpx.AsyncClient(headers=_YAHOO_HEADERS, timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise TickerValidationUnavailableError("Symbol validation timed out") from exc
    except httpx.RequestError as exc:
        raise TickerValidationUnavailableError("Symbol validation request failed") from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise TickerValidationUnavailableError(f"Symbol validation returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TickerValidationUnavailableError("Symbol validation returned invalid data") from exc
    if not isinstance(payload, dict):
        raise TickerValidationUnavailableError("Symbol validation returned invalid data")
    return payload

async def _fetch_quote_candidates(ticker: str) -> list[dict[str, Any]]:
    payload = await _request_yahoo_json(_YAHOO_QUOTE_URL, params={"symbols": ticker})
    if payload is None:
        return []
    response = payload.get("quoteResponse")
    if not isinstance(response, dict):
        return []
    results = response.get("result")
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []

async def _fetch_search_candidates(ticker: str) -> list[dict[str, Any]]:
    payload = await _request_yahoo_json(
        _YAHOO_SEARCH_URL,
        params={"q": ticker, "quotesCount": str(_MAX_SUGGESTIONS), "newsCount": "0"},
    )
    if payload is None:
        raise TickerValidationUnavailableError("Symbol search is unavailable")
    quotes = payload.get("quotes")
    return [item for item in quotes if isinstance(item, dict)] if isinstance(quotes, list) else []

def _candidate_symbol(candidate: dict[str, Any]) -> str | None:
    symbol = candidate.get("symbol")
    return symbol.strip().upper() if isinstance(symbol, str) and symbol.strip() else None

def _suggestions_from_candidates(candidates: list[dict[str, Any]], ticker: str) -> tuple[TickerSuggestion, ...]:
    suggestions: list[TickerSuggestion] = []
    seen: set[str] = {ticker}
    for candidate in candidates:
        symbol = _candidate_symbol(candidate)
        if symbol is None or symbol in seen:
            continue
        seen.add(symbol)
        name = candidate.get("longname") or candidate.get("shortname")
        quote_type = candidate.get("quoteType")
        suggestions.append(
            TickerSuggestion(
                symbol=symbol,
                name=name if isinstance(name, str) else None,
                quote_type=quote_type if isinstance(quote_type, str) else None,
            )
        )
        if len(suggestions) >= _MAX_SUGGESTIONS:
            break
    return tuple(suggestions)

def _cache_result(ticker: str, suggestions: tuple[TickerSuggestion, ...] | None) -> None:
    if suggestions is None:
        _VALID_CACHE[ticker] = True
    else:
        _INVALID_CACHE[ticker] = suggestions

async def _validate_normalized_ticker(normalized: str) -> TickerValidationResult:
    if normalized in _VALID_CACHE:
        return TickerValidationResult(ticker=normalized)
    cached_suggestions = _INVALID_CACHE.get(normalized)
    if cached_suggestions is not None:
        raise TickerNotFoundError(normalized, cached_suggestions)

    quote_failure: TickerValidationUnavailableError | None = None
    try:
        quote_candidates = await _fetch_quote_candidates(normalized)
    except TickerValidationUnavailableError as exc:
        quote_failure = exc
        quote_candidates = []
    if any(_candidate_symbol(candidate) == normalized for candidate in quote_candidates):
        _cache_result(normalized, None)
        return TickerValidationResult(ticker=normalized)

    try:
        search_candidates = await _fetch_search_candidates(normalized)
    except TickerValidationUnavailableError:
        if quote_failure is not None:
            raise quote_failure from None
        _cache_result(normalized, ())
        raise TickerNotFoundError(normalized) from None
    if any(_candidate_symbol(candidate) == normalized for candidate in search_candidates):
        _cache_result(normalized, None)
        return TickerValidationResult(ticker=normalized)

    suggestions = _suggestions_from_candidates(search_candidates, normalized)
    _cache_result(normalized, suggestions)
    raise TickerNotFoundError(normalized, suggestions)

async def validate_analysis_ticker(ticker: str, *, asset_type: str = "stock") -> TickerValidationResult:
    """Confirm that *ticker* exists before it can enter an analysis queue.

    ``asset_type`` is intentionally accepted for the API contract even though
    Yahoo's instrument taxonomy is broader than the two UI choices.  Rejecting
    a valid ETF, index, or token solely because Yahoo labels it differently
    would turn this guard into a false-negative source.
    """
    del asset_type
    return await _validate_normalized_ticker(_normalize_ticker(ticker))

async def validate_analysis_tickers(tickers: list[str], *, asset_type: str = "stock") -> list[TickerValidationResult]:
    """Validate a portfolio batch with bounded lookup concurrency.

    Results and exceptions are inspected in input order, so the API reports
    the first invalid symbol deterministically while never enqueueing a partial
    portfolio analysis.
    """
    normalized_tickers = [_normalize_ticker(ticker) for ticker in tickers]
    semaphore = asyncio.Semaphore(4)

    async def _validate_one(ticker: str) -> TickerValidationResult:
        async with semaphore:
            return await _validate_normalized_ticker(ticker)

    del asset_type
    results = await asyncio.gather(*(_validate_one(ticker) for ticker in normalized_tickers), return_exceptions=True)
    validated: list[TickerValidationResult] = []
    for result in results:
        if isinstance(result, BaseException):
            raise result
        validated.append(result)
    return validated
