import asyncio
import logging
import math

import httpx
import pandas as pd
import yfinance as yf

_logger = logging.getLogger(__name__)

_BATCH_PRICE_TIMEOUT_SEC = 10.0
_SINGLE_PRICE_TIMEOUT_SEC = 6.0
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


async def get_live_price(ticker: str) -> float | None:
    """Fetch live price for a single ticker. Falls back to history if Yahoo REST query fails."""
    # 1. Try direct REST query (fast, free, API key-less)
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker.upper()}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_YAHOO_HEADERS, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                if results:
                    price = (
                        results[0].get("regularMarketPrice")
                        or results[0].get("preMarketPrice")
                        or results[0].get("postMarketPrice")
                    )
                    if price is not None:
                        val = float(price)
                        if math.isfinite(val) and val > 0:
                            return val
    except Exception as e:
        _logger.warning("Direct Yahoo quote fetch failed for %s: %s", ticker, e)

    # 2. Fallback to Ticker.history (safe, yfinance-native)
    def _fallback():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                if math.isfinite(price) and price > 0:
                    return price
        except Exception as e:
            _logger.warning("History fallback failed for %s: %s", ticker, e)
        return None

    try:
        return await asyncio.wait_for(asyncio.to_thread(_fallback), timeout=_SINGLE_PRICE_TIMEOUT_SEC)
    except TimeoutError:
        _logger.warning("Price fetch fallback timed out for %s after %.1fs", ticker, _SINGLE_PRICE_TIMEOUT_SEC)
        return None


async def get_live_prices_batch(tickers: list[str]) -> dict[str, float]:
    """Fetch live prices for multiple tickers in a single batch call."""
    if not tickers:
        return {}

    unique = list(dict.fromkeys([t.upper() for t in tickers]))
    prices = await _fetch_yahoo_quotes_rest(unique)

    missing = [symbol for symbol in unique if symbol not in prices]
    if missing:
        fallback_res = await _fetch_yfinance_download_fallback(missing)
        prices.update(fallback_res)

        still_missing = [symbol for symbol in unique if symbol not in prices]
        if still_missing:
            prices.update(await _fetch_individual_fallbacks(still_missing))

    return prices


async def _fetch_yahoo_quotes_rest(unique_tickers: list[str]) -> dict[str, float]:
    """Fetch multiple quotes from Yahoo REST API."""
    prices: dict[str, float] = {}
    symbols_str = ",".join(unique_tickers)
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_YAHOO_HEADERS, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                for item in results:
                    symbol = item.get("symbol", "").upper()
                    price = item.get("regularMarketPrice") or item.get("preMarketPrice") or item.get("postMarketPrice")
                    if price is not None and symbol in unique_tickers:
                        val = float(price)
                        if math.isfinite(val) and val > 0:
                            prices[symbol] = val
    except Exception as exc:
        _logger.warning("Direct batch query failed for %s: %s", unique_tickers, exc)
    return prices


async def _fetch_yfinance_download_fallback(missing: list[str]) -> dict[str, float]:
    """Fallback batch yfinance download."""

    def _batch_fallback():
        fallback_prices = {}
        try:
            data = yf.download(
                missing if len(missing) > 1 else missing[0],
                period="2d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if data is not None and not getattr(data, "empty", False):
                close = data["Close"] if "Close" in data.columns else data
                if not getattr(close, "empty", False):
                    fallback_prices.update(_parse_yfinance_batch_data(close, missing))
        except Exception as exc:
            _logger.warning("Batch fallback download failed (%s): %s", missing, exc)
        return fallback_prices

    try:
        return await asyncio.wait_for(asyncio.to_thread(_batch_fallback), timeout=_BATCH_PRICE_TIMEOUT_SEC)
    except TimeoutError:
        _logger.warning("Batch fallback download timed out for %s", missing)
        return {}


def _parse_yfinance_batch_data(close_data, missing_symbols: list[str]) -> dict[str, float]:
    """Parse pandas data from yf.download."""
    parsed = {}
    rows = close_data.ffill()
    if rows.empty:
        return parsed

    if hasattr(close_data, "columns"):
        last_row = rows.iloc[-1]
        for symbol in missing_symbols:
            try:
                val = float(last_row[symbol])
                if math.isfinite(val) and val > 0:
                    parsed[symbol] = val
            except (KeyError, TypeError, ValueError):
                continue
    else:
        val = float(rows.iloc[-1])
        if math.isfinite(val) and val > 0:
            parsed[missing_symbols[0]] = val
    return parsed


async def _fetch_individual_fallbacks(still_missing: list[str]) -> dict[str, float]:
    """Final individual fallback for any remaining missing tickers."""
    prices = {}
    fallbacks = await asyncio.gather(*[get_live_price(symbol) for symbol in still_missing], return_exceptions=True)
    for symbol, fetched in zip(still_missing, fallbacks, strict=True):
        if isinstance(fetched, BaseException) or fetched is None:
            continue
        val = float(fetched)
        if math.isfinite(val) and val > 0:
            prices[symbol] = val
    return prices


async def get_historical_data(ticker: str, start_date: str, end_date: str):
    """Fetch historical OHLCV data for a ticker."""
    max_retries = 3
    delay = 1.0
    for attempt in range(max_retries):
        try:

            def _fetch():
                data = yf.Ticker(ticker).history(start=start_date, end=end_date)
                if data.empty:
                    return data

                # Handle MultiIndex columns (common in newer yfinance versions)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                if data.index.tz is not None:
                    data.index = data.index.tz_localize(None)

                # Ensure data is sorted by date and remove any duplicates
                data = data[~data.index.duplicated(keep="last")]
                data = data.sort_index()
                return data

            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            if attempt < max_retries - 1:
                _logger.warning(
                    "Historical data fetch for %s failed on attempt %d: %s. Retrying in %.1fs...",
                    ticker,
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2
            else:
                _logger.exception("Historical data fetch for %s failed after %d attempts", ticker, max_retries)
                raise


async def calculate_returns(
    ticker: str, start_date: str, holding_days: int = 5, benchmark: str = "SPY"
) -> tuple[float | None, float | None, int | None]:
    """
    Calculate raw return and alpha vs benchmark for a given ticker and start date.
    Returns: (raw_return, alpha_return, actual_holding_days)
    """

    def _fetch():
        try:
            from datetime import datetime, timedelta

            start = datetime.strptime(start_date, "%Y-%m-%d")
            # Buffer for weekends/holidays
            end = start + timedelta(days=holding_days + 7)
            end_str = end.strftime("%Y-%m-%d")

            stock = yf.Ticker(ticker).history(start=start_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=start_date, end=end_str)

            if stock.empty or bench.empty:
                return None, None, None

            # Drop NaNs to prevent returning NaN if last/current day has NaN values
            stock_close = stock["Close"].dropna()
            bench_close = bench["Close"].dropna()

            if len(stock_close) < 2 or len(bench_close) < 2:
                return None, None, None

            actual = min(holding_days, len(stock_close) - 1, len(bench_close) - 1)
            raw = float((stock_close.iloc[actual] - stock_close.iloc[0]) / stock_close.iloc[0])
            bench_r = float((bench_close.iloc[actual] - bench_close.iloc[0]) / bench_close.iloc[0])

            import math

            if math.isnan(raw) or math.isnan(bench_r):
                return None, None, None

            return round(raw, 4), round(raw - bench_r, 4), actual
        except Exception as e:
            _logger.warning("Return calculation failed for %s on %s: %s", ticker, start_date, e)
            return None, None, None

    return await asyncio.to_thread(_fetch)


async def get_benchmark_return(
    benchmark: str = "SPY",
    period: str = "1y",
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> float | None:
    """Calculate a simple benchmark return for a relative or explicit period.

    ``period`` remains available for existing callers.  An explicit start date
    is needed when comparing a portfolio's lifetime return with its benchmark;
    a fixed ``1y`` return is not comparable to a portfolio opened at another
    time.
    """

    def _fetch():
        try:
            history_args = {"period": period}
            if start_date:
                history_args = {"start": start_date}
                if end_date:
                    history_args["end"] = end_date
            spy = yf.Ticker(benchmark).history(**history_args)
            if not spy.empty:
                # Drop NaNs to prevent returning NaN if last/current day has NaN values
                close_series = spy["Close"].dropna()
                if len(close_series) >= 2:
                    ret = float((close_series.iloc[-1] - close_series.iloc[0]) / close_series.iloc[0] * 100)
                    import math

                    if not math.isnan(ret):
                        return ret
            return None
        except Exception as exc:
            _logger.warning(
                "Benchmark return fetch failed for %s (start=%s, end=%s, period=%s): %s",
                benchmark,
                start_date,
                end_date,
                period,
                exc,
            )
            return None

    return await asyncio.to_thread(_fetch)


async def get_live_prices_details_batch(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Fetch live prices and daily change percentage for multiple tickers in a single batch call."""
    if not tickers:
        return {}

    unique = list(dict.fromkeys([t.upper() for t in tickers]))
    details: dict[str, dict[str, float]] = {}

    symbols_str = ",".join(unique)
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_YAHOO_HEADERS, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                for item in results:
                    symbol = item.get("symbol", "").upper()
                    price = item.get("regularMarketPrice") or item.get("preMarketPrice") or item.get("postMarketPrice")
                    change_percent = item.get("regularMarketChangePercent", 0.0)
                    if price is not None and symbol in unique:
                        details[symbol] = {
                            "price": float(price),
                            "change_percent": float(change_percent),
                        }
    except Exception as exc:
        _logger.warning("Direct batch details query failed for %s: %s", unique, exc)

    # Fallback to standard price batch helper for any missing tickers
    missing = [symbol for symbol in unique if symbol not in details]
    if missing:
        fallback_prices = await get_live_prices_batch(missing)
        for symbol, price in fallback_prices.items():
            details[symbol] = {
                "price": price,
                "change_percent": 0.0,
            }

    return details
