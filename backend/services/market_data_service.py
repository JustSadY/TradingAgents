import asyncio
import logging
import math

import httpx
import pandas as pd
import yfinance as yf

_logger = logging.getLogger(__name__)

_BATCH_PRICE_TIMEOUT_SEC = 10.0
_SINGLE_PRICE_TIMEOUT_SEC = 6.0


async def get_live_price(ticker: str) -> float | None:
    """Fetch live price for a single ticker. Falls back to history if Yahoo REST query fails."""
    # 1. Try direct REST query (fast, free, API key-less)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker.upper()}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=5.0)
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
                if price is not None:
                    val = float(price)
                    if math.isfinite(val) and val > 0:
                        return val
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
    prices: dict[str, float] = {}

    # 1. Try direct REST batch query (fast, single HTTP call for all tickers)
    symbols_str = ",".join(unique)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                for item in results:
                    symbol = item.get("symbol", "").upper()
                    price = item.get("regularMarketPrice") or item.get("preMarketPrice") or item.get("postMarketPrice")
                    if price is not None and symbol in unique:
                        val = float(price)
                        if math.isfinite(val) and val > 0:
                            prices[symbol] = val
    except Exception as exc:
        _logger.debug("Direct batch query failed for %s: %s", unique, exc)

    # 2. If any tickers are missing, download via yfinance or use get_live_price fallback
    missing = [symbol for symbol in unique if symbol not in prices]
    if missing:
        # Fallback batch yfinance download
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
                        if hasattr(close, "columns"):
                            rows = close.ffill()
                            if not rows.empty:
                                last_row = rows.iloc[-1]
                                for symbol in missing:
                                    try:
                                        raw = last_row[symbol]
                                        val = float(raw)
                                        if math.isfinite(val) and val > 0:
                                            fallback_prices[symbol] = val
                                    except (KeyError, TypeError, ValueError):
                                        continue
                        else:
                            rows = close.ffill()
                            if not rows.empty:
                                val = float(rows.iloc[-1])
                                if math.isfinite(val) and val > 0:
                                    fallback_prices[missing[0]] = val
            except Exception as exc:
                _logger.debug("Batch fallback download failed (%s): %s", missing, exc)
            return fallback_prices

        try:
            fallback_res = await asyncio.wait_for(asyncio.to_thread(_batch_fallback), timeout=_BATCH_PRICE_TIMEOUT_SEC)
            prices.update(fallback_res)
        except TimeoutError:
            _logger.warning("Batch fallback download timed out for %s", missing)

        # 3. Final individual fallback for any remaining missing tickers
        still_missing = [symbol for symbol in unique if symbol not in prices]
        if still_missing:
            fallbacks = await asyncio.gather(
                *[get_live_price(symbol) for symbol in still_missing], return_exceptions=True
            )
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
                _logger.error("Historical data fetch for %s failed after %d attempts: %s", ticker, max_retries, exc)
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
            _logger.debug("Return calculation failed for %s on %s: %s", ticker, start_date, e)
            return None, None, None

    return await asyncio.to_thread(_fetch)


async def get_benchmark_return(benchmark: str = "SPY", period: str = "1y") -> float | None:
    """Calculate simple return for a benchmark over a period."""

    def _fetch():
        try:
            spy = yf.Ticker(benchmark).history(period=period)
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
            _logger.warning("Benchmark return fetch failed for %s (period=%s): %s", benchmark, period, exc)
            return None

    return await asyncio.to_thread(_fetch)


async def get_live_prices_details_batch(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Fetch live prices and daily change percentage for multiple tickers in a single batch call."""
    if not tickers:
        return {}

    unique = list(dict.fromkeys([t.upper() for t in tickers]))
    details: dict[str, dict[str, float]] = {}

    symbols_str = ",".join(unique)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=8.0)
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
        _logger.debug("Direct batch details query failed for %s: %s", unique, exc)

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
