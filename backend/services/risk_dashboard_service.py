from __future__ import annotations

import asyncio
import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.services.indicator_service import fetch_sector

_EMPTY_DASHBOARD = {
    "beta": None,
    "volatility": None,
    "sector_weights": [],
    "correlation": [],
    "holdings_risk": [],
    "message": "No open positions",
}


def _prepare_holdings(holdings: list[dict]) -> float:
    """Annotate each holding with a numeric ``_market_value``; return total equity.

    Equity is floored to 1.0 when (near-)zero so weight divisions stay finite.
    """
    for h in holdings:
        market_value = h.get("market_value")
        if market_value is None:
            qty = float(h.get("quantity", 0))
            price = float(h.get("current_price", 0))
            h["_market_value"] = qty * price
        else:
            h["_market_value"] = float(market_value)

    total_equity = sum(h["_market_value"] for h in holdings)
    return total_equity if abs(total_equity) >= 1e-9 else 1.0


async def _fetch_close_history(ticker: str, period: str = "3mo"):
    """Fetch a ticker's close-price series off-thread; ``None`` on any failure."""
    try:
        import yfinance as yf

        return await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).history(period=period)["Close"])
    except Exception:
        return None


def _spy_returns(spy_hist_raw: Any):
    """Daily SPY returns when at least 10 observations exist, else ``None``."""
    if isinstance(spy_hist_raw, Exception) or spy_hist_raw is None:
        return None
    try:
        spy_ret = spy_hist_raw.pct_change().dropna()
        if len(spy_ret) >= 10:
            return spy_ret
    except Exception:
        return None
    return None


async def _fetch_market_data(tickers: list[str]) -> tuple[dict[str, Any], Any, dict[str, str]]:
    """Concurrently fetch per-ticker close history, SPY history, and sectors.

    Returns ``(ticker_hist, spy_returns, sector_map)`` with failed fetches simply
    omitted from the maps.
    """

    async def hist_for(ticker: str):
        return ticker, await _fetch_close_history(ticker)

    async def sector_for(ticker: str):
        return ticker, await fetch_sector(ticker)

    results = await asyncio.gather(
        *[hist_for(t) for t in tickers],
        _fetch_close_history("SPY"),
        *[sector_for(t) for t in tickers],
        return_exceptions=True,
    )

    n = len(tickers)
    history_results = results[:n]
    spy_hist_raw = results[n]
    sector_results = results[n + 1 :]

    ticker_hist: dict[str, Any] = {}
    for res in history_results:
        if isinstance(res, Exception):
            continue
        ticker, hist = res
        ticker_hist[ticker] = hist

    sector_map: dict[str, str] = {}
    for res in sector_results:
        if isinstance(res, Exception):
            continue
        ticker, sector = res
        sector_map[ticker] = sector

    return ticker_hist, _spy_returns(spy_hist_raw), sector_map


def _beta_vs_spy(daily_ret: Any, spy_returns: Any) -> float | None:
    """Beta of a return series against SPY over their overlapping >=10-day window."""
    if spy_returns is None:
        return None
    common_idx = daily_ret.index.intersection(spy_returns.index)
    if len(common_idx) < 10:
        return None
    stock_aligned = daily_ret.loc[common_idx]
    spy_aligned = spy_returns.loc[common_idx]
    cov = float(stock_aligned.cov(spy_aligned))
    var_spy = float(spy_aligned.var())
    if abs(var_spy) > 1e-9:
        return round(cov / var_spy, 4)
    return None


def _holding_vol_beta(hist: Any, spy_returns: Any) -> tuple[Any, float | None, float | None]:
    """Compute ``(daily_returns, annual_volatility, beta)`` from a close series.

    ``daily_returns`` is returned whenever there are >=2 observations — even if
    the later vol/beta math fails — so correlation still sees the series (matches
    the original ordering).
    """
    if hist is None:
        return None, None, None
    try:
        daily_ret = hist.pct_change().dropna()
    except Exception:
        return None, None, None
    if len(daily_ret) < 2:
        return None, None, None

    vol_annual: float | None = None
    beta: float | None = None
    try:
        std_daily = float(daily_ret.std())
        vol_annual = round(std_daily * math.sqrt(252), 4)
        beta = _beta_vs_spy(daily_ret, spy_returns)
    except Exception:
        pass
    return daily_ret, vol_annual, beta


def _build_holdings_risk(
    holdings: list[dict],
    ticker_hist: dict[str, Any],
    spy_returns: Any,
    sector_map: dict[str, str],
    total_equity: float,
) -> tuple[list[dict], float | None, float | None, dict[str, Any]]:
    """Per-holding risk rows plus weight-averaged portfolio beta/volatility.

    Also returns the per-ticker daily-return series for correlation.
    """
    holdings_risk: list[dict] = []
    ticker_returns: dict[str, Any] = {}
    beta_num = beta_den = vol_num = vol_den = 0.0

    for h in holdings:
        ticker = h["ticker"]
        weight = h["_market_value"] / total_equity
        sector = sector_map.get(ticker, "Unknown")

        daily_ret, vol_annual, beta = _holding_vol_beta(ticker_hist.get(ticker), spy_returns)
        if daily_ret is not None:
            ticker_returns[ticker] = daily_ret
        if vol_annual is not None:
            vol_num += weight * vol_annual
            vol_den += weight
        if beta is not None:
            beta_num += weight * beta
            beta_den += weight

        holdings_risk.append(
            {
                "ticker": ticker,
                "weight_pct": round(weight * 100.0, 4),
                "volatility_annual": vol_annual,
                "beta": beta,
                "sector": sector,
            }
        )

    holdings_risk.sort(key=lambda x: x["weight_pct"], reverse=True)
    portfolio_beta = round(beta_num / beta_den, 4) if beta_den > 0 else None
    portfolio_volatility = round(vol_num / vol_den, 4) if vol_den > 0 else None
    return holdings_risk, portfolio_beta, portfolio_volatility, ticker_returns


def _build_sector_weights(
    holdings: list[dict], sector_map: dict[str, str], total_equity: float
) -> list[dict]:
    """Aggregate market value by sector into descending weight-percent rows."""
    sector_values: dict[str, float] = {}
    for h in holdings:
        s = sector_map.get(h["ticker"], "Unknown")
        sector_values[s] = sector_values.get(s, 0.0) + h["_market_value"]

    sector_weights = [
        {"sector": s, "weight_pct": round(mv / total_equity * 100.0, 4)} for s, mv in sector_values.items()
    ]
    sector_weights.sort(key=lambda x: x["weight_pct"], reverse=True)
    return sector_weights


def _build_correlation_matrix(ticker_returns: dict[str, Any]) -> list[dict]:
    """Pairwise return correlations over each pair's overlapping >=10-day window."""
    correlation: list[dict] = []
    ticker_list = list(ticker_returns.keys())
    for ta in ticker_list:
        for tb in ticker_list:
            if ta == tb:
                continue
            ret_a = ticker_returns[ta]
            ret_b = ticker_returns[tb]
            common = ret_a.index.intersection(ret_b.index)
            if len(common) < 10:
                continue
            try:
                corr = float(ret_a.loc[common].corr(ret_b.loc[common]))
                if not math.isnan(corr):
                    correlation.append({"ticker_a": ta, "ticker_b": tb, "correlation": round(corr, 3)})
            except Exception:
                pass
    return correlation


async def _fetch_returns(tickers: list[str]) -> dict[str, Any]:
    """Fetch 3mo daily returns per ticker; failed/short series are omitted."""
    results = await asyncio.gather(*[_fetch_close_history(t) for t in tickers], return_exceptions=True)
    out: dict[str, Any] = {}
    for ticker, hist in zip(tickers, results, strict=False):
        if isinstance(hist, Exception) or hist is None:
            continue
        try:
            r = hist.pct_change().dropna()
            if len(r) >= 2:
                out[ticker] = r
        except Exception:
            continue
    return out


async def correlated_notional(ticker: str, holdings: list[dict], threshold: float = 0.3) -> float:
    """Correlation-weighted notional of *other* holdings that move with ``ticker``.

    Σ over held names (excluding ``ticker``) of ``corr * market_value`` for names
    whose return correlation with ``ticker`` exceeds ``threshold``. Best-effort:
    returns 0.0 on any data failure so it can never block trading.
    """
    others = [h for h in holdings if h.get("ticker") and h["ticker"] != ticker]
    if not others:
        return 0.0
    try:
        returns = await _fetch_returns([ticker] + [h["ticker"] for h in others])
    except Exception:
        return 0.0
    base = returns.get(ticker)
    if base is None:
        return 0.0

    total = 0.0
    for h in others:
        r = returns.get(h["ticker"])
        if r is None:
            continue
        common = base.index.intersection(r.index)
        if len(common) < 10:
            continue
        try:
            corr = float(base.loc[common].corr(r.loc[common]))
        except Exception:
            continue
        if corr > threshold:
            total += corr * float(h.get("market_value") or 0.0)
    return total


async def get_risk_dashboard(db: AsyncSession, user: User) -> dict:
    """Calculate portfolio risk metrics from current open holdings."""
    from backend.services.mock_trading_service import get_portfolio_with_live_prices

    portfolio_data: dict = await get_portfolio_with_live_prices(db, user=user)
    holdings: list[dict] = portfolio_data.get("holdings", [])
    if not holdings:
        return dict(_EMPTY_DASHBOARD)

    total_equity = _prepare_holdings(holdings)
    tickers = [h["ticker"] for h in holdings]

    ticker_hist, spy_returns, sector_map = await _fetch_market_data(tickers)

    holdings_risk, portfolio_beta, portfolio_volatility, ticker_returns = _build_holdings_risk(
        holdings, ticker_hist, spy_returns, sector_map, total_equity
    )
    sector_weights = _build_sector_weights(holdings, sector_map, total_equity)
    correlation = _build_correlation_matrix(ticker_returns)

    return {
        "beta": portfolio_beta,
        "volatility": portfolio_volatility,
        "sector_weights": sector_weights,
        "correlation": correlation,
        "holdings_risk": holdings_risk,
    }
