import asyncio
import logging
from typing import Any

_logger = logging.getLogger(__name__)


def _download_and_correlate(tickers: list[str], period: str) -> tuple[Any, list[str] | None]:
    import yfinance as yf

    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    if data.empty:
        return None, None

    if len(tickers) == 1:
        close = data[["Close"]] if "Close" in data.columns else data
        close.columns = tickers
    else:
        if "Close" in data.columns:
            close = data["Close"]
        else:
            close = data

    close = close.dropna(axis=1, how="all")
    if close.shape[1] < 2:
        return None, None

    corr = close.corr().round(3)
    return corr, close.columns.tolist()


async def compute_correlation_matrix(tickers: list[str], period: str) -> dict[str, Any]:
    if len(tickers) < 2:
        return {
            "tickers": tickers,
            "matrix": [],
            "avg_correlation": None,
            "warning": "Need at least 2 holdings",
        }

    loop = asyncio.get_event_loop()
    corr_df, available_tickers = await loop.run_in_executor(None, _download_and_correlate, tickers, period)

    if corr_df is None:
        return {
            "tickers": tickers,
            "matrix": [],
            "avg_correlation": None,
            "warning": "Could not download price data",
        }

    matrix = corr_df.values.tolist()
    n = len(available_tickers)
    off_diag_values = [corr_df.iloc[i, j] for i in range(n) for j in range(n) if i != j]
    avg_corr = round(sum(off_diag_values) / len(off_diag_values), 3) if off_diag_values else None

    return {
        "tickers": available_tickers,
        "matrix": matrix,
        "avg_correlation": avg_corr,
        "warning": None,
    }
