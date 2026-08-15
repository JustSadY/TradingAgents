"""Research/reference integrations that are not production fallbacks.

Production LLM routing, technical indicators, broker execution and checkpoint
persistence are package-backed directly in their owning services. The helpers
here are deliberately isolated research/validation tools.
"""

from __future__ import annotations

import asyncio
from importlib.util import find_spec
from typing import Any

import numpy as np
import pandas as pd

_OPTIONAL_PACKAGES = {
    "openbb": "openbb",
    "talib": "talib",
    "vectorbt": "vectorbt",
    "empyrical": "empyrical",
    "quantstats": "quantstats",
    "pypfopt": "pypfopt",
    "opentelemetry": "opentelemetry",
}


def optional_dependency_status() -> dict[str, bool]:
    return {name: find_spec(module) is not None for name, module in _OPTIONAL_PACKAGES.items()}


async def openbb_historical(
    symbol: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    provider: str | None = None,
) -> pd.DataFrame:
    """Fetch an OpenBB research data set without mutating application caches."""
    try:
        from openbb import obb
    except ImportError as exc:
        raise RuntimeError("OpenBB is not installed") from exc

    def _fetch() -> pd.DataFrame:
        kwargs: dict[str, Any] = {"symbol": symbol.upper()}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if provider:
            kwargs["provider"] = provider
        frame = obb.equity.price.historical(**kwargs).to_df().copy()
        frame.index = pd.to_datetime(frame.index)
        frame = frame.rename(
            columns={name: name.capitalize() for name in ("open", "high", "low", "close", "volume")}
        )
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"OpenBB result missing OHLCV columns: {missing}")
        return frame[required].sort_index()

    return await asyncio.to_thread(_fetch)


def talib_standard_indicators(df: pd.DataFrame, *, period: int = 14) -> dict[str, pd.Series]:
    """Calculate a TA-Lib oracle for research/parity checks only."""
    try:
        import talib
    except ImportError as exc:
        raise RuntimeError("TA-Lib is not installed") from exc

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)
    macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    typical = (high + low + close) / 3.0
    rolling_value = (typical * volume).rolling(period, min_periods=period).sum()
    rolling_volume = volume.rolling(period, min_periods=period).sum().replace(0, np.nan)
    return {
        "rsi": pd.Series(talib.RSI(close, timeperiod=period), index=df.index),
        "macd": pd.Series(macd, index=df.index),
        "macd_signal": pd.Series(macd_signal, index=df.index),
        "macd_hist": pd.Series(macd_hist, index=df.index),
        "adx": pd.Series(talib.ADX(high, low, close, timeperiod=period), index=df.index),
        "atr": pd.Series(talib.ATR(high, low, close, timeperiod=period), index=df.index),
        "vwap": rolling_value / rolling_volume,
    }


def vectorbt_reference_backtest(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    *,
    initial_cash: float = 100_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> dict[str, float]:
    """Run vectorbt as a research oracle, never as the production execution engine."""
    try:
        import vectorbt as vbt
    except ImportError as exc:
        raise RuntimeError("vectorbt is not installed") from exc

    portfolio = vbt.Portfolio.from_signals(
        close.astype(float),
        entries=entries.astype(bool),
        exits=exits.astype(bool),
        init_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        freq="1D",
    )
    return {
        "total_return": float(portfolio.total_return()),
        "sharpe_ratio": float(portfolio.sharpe_ratio()),
        "max_drawdown": float(portfolio.max_drawdown()),
        "final_value": float(portfolio.final_value()),
    }


def cross_validate_return_metrics(returns: pd.Series) -> dict[str, dict[str, float]]:
    """Cross-check return metrics with empyrical and QuantStats when installed."""
    clean = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    result: dict[str, dict[str, float]] = {}
    try:
        import empyrical as ep

        result["empyrical"] = {
            "annual_return": float(ep.annual_return(clean)),
            "sharpe_ratio": float(ep.sharpe_ratio(clean)),
            "sortino_ratio": float(ep.sortino_ratio(clean)),
            "max_drawdown": float(ep.max_drawdown(clean)),
        }
    except ImportError:
        pass
    try:
        import quantstats as qs

        result["quantstats"] = {
            "sharpe_ratio": float(qs.stats.sharpe(clean)),
            "sortino_ratio": float(qs.stats.sortino(clean)),
            "max_drawdown": float(qs.stats.max_drawdown(clean)),
        }
    except ImportError:
        pass
    return result


def pypfopt_target_weights(
    expected_returns: pd.Series,
    covariance: pd.DataFrame,
    *,
    risk_free_rate: float = 0.0,
) -> dict[str, float]:
    """Produce deterministic max-Sharpe research weights with PyPortfolioOpt."""
    try:
        from pypfopt.efficient_frontier import EfficientFrontier
    except ImportError as exc:
        raise RuntimeError("PyPortfolioOpt is not installed") from exc

    frontier = EfficientFrontier(expected_returns, covariance)
    frontier.max_sharpe(risk_free_rate=risk_free_rate)
    return {str(k): float(v) for k, v in frontier.clean_weights().items()}
