"""Screener agent: scan a ticker universe for candidates worth analysing.

Computes fast, deterministic technical scores (no LLM calls, one batch download)
so it can sweep dozens of tickers cheaply. Each ticker gets a composite score
from momentum, trend, volume surge, and RSI positioning; the top results are
returned as "add to watchlist / run analysis" candidates.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

_logger = logging.getLogger(__name__)

# A compact default universe of liquid large caps; users can pass their own.
DEFAULT_UNIVERSE = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "JPM",
    "V",
    "UNH",
    "XOM",
    "LLY",
    "COST",
    "HD",
    "NFLX",
    "CRM",
    "ORCL",
    "ADBE",
]
MAX_UNIVERSE = 50


@dataclass
class ScreenResult:
    ticker: str
    score: float
    momentum_1m_pct: float
    trend: str  # above/below 50-day SMA
    volume_surge: float  # last-5-day avg volume / 60-day avg volume
    rsi_14: float
    signals: list[str]


def _rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return float(value) if not math.isnan(value) else 50.0


def _score_ticker(ticker: str, df: pd.DataFrame) -> ScreenResult | None:
    closes = df["Close"].dropna()
    volumes = df["Volume"].dropna()
    if len(closes) < 60 or len(volumes) < 60:
        return None

    last = float(closes.iloc[-1])
    month_ago = float(closes.iloc[-21]) if len(closes) >= 21 else float(closes.iloc[0])
    momentum_1m = ((last - month_ago) / month_ago * 100.0) if month_ago else 0.0

    sma50 = float(closes.rolling(50).mean().iloc[-1])
    trend = "above_sma50" if last > sma50 else "below_sma50"

    vol_recent = float(volumes.iloc[-5:].mean())
    vol_base = float(volumes.iloc[-60:].mean())
    volume_surge = (vol_recent / vol_base) if vol_base else 1.0

    rsi = _rsi(closes)

    signals: list[str] = []
    score = 0.0
    # Momentum: reward strong (but not parabolic) 1-month moves.
    if momentum_1m > 5:
        score += min(momentum_1m, 25) / 25 * 35
        signals.append("strong_momentum")
    elif momentum_1m < -10:
        # Big drawdowns can be mean-reversion setups when RSI is washed out.
        if rsi < 30:
            score += 25
            signals.append("oversold_reversal")
    # Trend: price above the 50-day adds confirmation.
    if trend == "above_sma50":
        score += 20
        signals.append("uptrend")
    # Volume surge: unusual activity often precedes news/moves.
    if volume_surge > 1.5:
        score += min(volume_surge, 3.0) / 3.0 * 25
        signals.append("volume_surge")
    # RSI positioning: penalise overbought, mildly reward the healthy band.
    if 45 <= rsi <= 65:
        score += 10
    elif rsi > 75:
        score -= 10
        signals.append("overbought")

    return ScreenResult(
        ticker=ticker,
        score=round(score, 1),
        momentum_1m_pct=round(momentum_1m, 2),
        trend=trend,
        volume_surge=round(volume_surge, 2),
        rsi_14=round(rsi, 1),
        signals=signals,
    )


async def run_screen(universe: list[str] | None = None, top_n: int = 10) -> list[dict]:
    """Score ``universe`` (default: liquid large caps) and return the top candidates."""
    tickers = [t.strip().upper() for t in (universe or DEFAULT_UNIVERSE) if t and t.strip()]
    tickers = list(dict.fromkeys(tickers))[:MAX_UNIVERSE]
    if not tickers:
        return []

    def _download() -> pd.DataFrame:
        return yf.download(
            tickers=" ".join(tickers),
            period="6mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

    data = await asyncio.to_thread(_download)
    results: list[ScreenResult] = []
    for ticker in tickers:
        try:
            df = data[ticker] if len(tickers) > 1 else data
            if df is None or df.empty:
                continue
            scored = _score_ticker(ticker, df)
            if scored is not None:
                results.append(scored)
        # skip bad tickers, keep the sweep going
        except Exception as exc:  # noqa: BLE001
            _logger.debug("Screener skipped %s: %s", ticker, exc)

    results.sort(key=lambda r: r.score, reverse=True)
    return [
        {
            "ticker": r.ticker,
            "score": r.score,
            "momentum_1m_pct": r.momentum_1m_pct,
            "trend": r.trend,
            "volume_surge": r.volume_surge,
            "rsi_14": r.rsi_14,
            "signals": r.signals,
        }
        for r in results[: max(1, min(top_n, MAX_UNIVERSE))]
    ]
