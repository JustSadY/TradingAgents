import logging
import time

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from .cache import APICache
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)


def yf_retry(func, max_retries=3, base_delay=2.0):
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                raise


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
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
    curr_date_dt = pd.to_datetime(curr_date)
    start_date = curr_date_dt - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_date = curr_date_dt + pd.DateOffset(days=1)
    end_str = end_date.strftime("%Y-%m-%d")
    data = yf_retry(
        lambda: yf.download(
            symbol,
            start=start_str,
            end=end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        )
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


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]
