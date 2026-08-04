import logging
import threading
import time

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTickerMissingError

from backend.core.utils import safe_ticker_component

from .cache import APICache

logger = logging.getLogger(__name__)

_MISSING_TICKER_COOLDOWN_SECONDS = 300.0
_missing_ticker_lock = threading.Lock()
_missing_tickers: dict[str, tuple[float, str]] = {}

class YFinanceTickerUnavailableError(RuntimeError):
    """Yahoo reported a ticker as unavailable, or its short cooldown is active."""

    def __init__(self, ticker: str, reason: str, retry_after: float, *, from_cooldown: bool):
        self.ticker = ticker
        self.reason = reason
        self.retry_after = max(0.0, retry_after)
        self.from_cooldown = from_cooldown
        source = "cached unavailable response" if from_cooldown else "unavailable response"
        super().__init__(
            f"Yahoo Finance {source} for '{ticker}' ({reason}); retry after roughly {self.retry_after:.0f}s."
        )

def _ticker_key(ticker: str | None) -> str | None:
    if not isinstance(ticker, str):
        return None
    normalized = ticker.strip().upper()
    return normalized or None

def _get_missing_ticker_cooldown(ticker: str) -> tuple[float, str] | None:
    now = time.monotonic()
    with _missing_ticker_lock:
        entry = _missing_tickers.get(ticker)
        if entry is None:
            return None
        expires_at, reason = entry
        if expires_at <= now:
            _missing_tickers.pop(ticker, None)
            return None
        return expires_at - now, reason

def _remember_missing_ticker(ticker: str, reason: str) -> None:
    with _missing_ticker_lock:
        _missing_tickers[ticker] = (time.monotonic() + _MISSING_TICKER_COOLDOWN_SECONDS, reason)

def reset_yfinance_ticker_cooldowns() -> None:
    """Clear process-local unavailable-ticker state (primarily useful in tests)."""
    with _missing_ticker_lock:
        _missing_tickers.clear()

def yf_retry(func, max_retries=3, base_delay=2.0, *, ticker: str | None = None):
    """Run a Yahoo request with transient retries and ticker-missing cooldown.

    ``yf.download`` often logs an invalid symbol internally and returns an
    empty frame, while ``Ticker.history(..., raise_errors=True)`` gives us a
    typed missing-ticker error.  Once that error is observed, skip repeat
    Yahoo requests for the same ticker briefly.  The error still propagates so
    ``route_to_vendor`` can try an alternate vendor; it is never cached as
    market data.
    """
    ticker_key = _ticker_key(ticker)
    if ticker_key is not None:
        cached = _get_missing_ticker_cooldown(ticker_key)
        if cached is not None:
            retry_after, reason = cached
            raise YFinanceTickerUnavailableError(ticker_key, reason, retry_after, from_cooldown=True)

    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFTickerMissingError as exc:
            if ticker_key is None or isinstance(exc, YFPricesMissingError):
                raise
            reason = str(exc)
            _remember_missing_ticker(ticker_key, reason)
            raise YFinanceTickerUnavailableError(
                ticker_key,
                reason,
                _MISSING_TICKER_COOLDOWN_SECONDS,
                from_cooldown=False,
            ) from exc
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Yahoo Finance connection error, retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries}): {exc}"
                )
                time.sleep(delay)
            else:
                raise

def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(data["Date"], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    data["Date"] = dates
    data = data.dropna(subset=["Date"])
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()
    return data

def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    safe_ticker_component(symbol)
    cache_payload = APICache.get("stockstats_load_ohlcv", symbol, curr_date)
    if isinstance(cache_payload, dict) and cache_payload.get("rows"):
        cached_df = pd.DataFrame(cache_payload["rows"])
        if not cached_df.empty:
            return _clean_dataframe(cached_df)
    curr_date_dt = pd.Timestamp(curr_date).normalize()
    start_date = curr_date_dt - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_date = curr_date_dt + pd.DateOffset(days=1)
    end_str = end_date.strftime("%Y-%m-%d")
    data = yf_retry(
        lambda: yf.Ticker(symbol.upper()).history(
            start=start_str,
            end=end_str,
            auto_adjust=True,
            actions=False,
            raise_errors=True,
        ),
        ticker=symbol,
    )
    if "Date" not in data.columns:
        if data.index.name != "Date":
            data.index.name = "Date"
        data = data.reset_index()
    data = _clean_dataframe(data)
    data = data[data["Date"] <= curr_date_dt]
    payload = data.copy()
    payload["Date"] = payload["Date"].dt.strftime("%Y-%m-%d")
    APICache.set("stockstats_load_ohlcv", {"rows": payload.to_dict(orient="records")}, symbol, curr_date)
    return data

def filter_financials_by_date(
    data: pd.DataFrame,
    curr_date: str,
    *,
    frequency: str = "quarterly",
) -> pd.DataFrame:
    """Apply a conservative information-availability cutoff.

    Yahoo exposes period-end columns, not the date the statement became public.
    Treating a March 31 quarter as known on March 31 is look-ahead bias.  Until
    a provider supplies filing/accepted dates, use a conservative publication
    lag (45 days quarterly, 90 days annual) and fail closed around the boundary.
    """
    if not curr_date or data.empty:
        return data
    lag_days = 45 if str(frequency).lower() == "quarterly" else 90
    cutoff = pd.Timestamp(curr_date) - pd.Timedelta(days=lag_days)
    columns = pd.to_datetime(data.columns, errors="coerce")
    mask = columns.notna() & (columns <= cutoff)
    return data.loc[:, mask]
