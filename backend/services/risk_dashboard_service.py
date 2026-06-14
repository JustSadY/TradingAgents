from __future__ import annotations

import asyncio
import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


async def get_risk_dashboard(db: AsyncSession, user: User) -> dict:
    """Calculate portfolio risk metrics from current open holdings."""

    from backend.services.mock_trading_service import get_portfolio_with_live_prices

    portfolio_data: dict = await get_portfolio_with_live_prices(db, user=user)

    holdings: list[dict] = portfolio_data.get("holdings", [])

    if not holdings:
        return {
            "beta": None,
            "volatility": None,
            "sector_weights": [],
            "correlation": [],
            "holdings_risk": [],
            "message": "No open positions",
        }

    # Compute market values and total equity
    for h in holdings:
        market_value = h.get("market_value")
        if market_value is None:
            # Fallback: quantity * current_price
            qty = float(h.get("quantity", 0))
            price = float(h.get("current_price", 0))
            h["_market_value"] = qty * price
        else:
            h["_market_value"] = float(market_value)

    total_equity = sum(h["_market_value"] for h in holdings)
    if total_equity == 0.0:
        total_equity = 1.0  # prevent division by zero

    tickers: list[str] = [h["ticker"] for h in holdings]

    # ---- Fetch price histories in parallel ----

    async def _fetch_history(ticker: str):
        try:
            import yfinance as yf

            hist = await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).history(period="3mo")["Close"])
            return ticker, hist
        except Exception:
            return ticker, None

    async def _fetch_spy_history():
        try:
            import yfinance as yf

            hist = await asyncio.to_thread(lambda: yf.Ticker("SPY").history(period="3mo")["Close"])
            return hist
        except Exception:
            return None

    async def _fetch_sector(ticker: str):
        try:
            import yfinance as yf

            info = await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).info)
            return ticker, info.get("sector", "Unknown")
        except Exception:
            return ticker, "Unknown"

    # Launch all fetches concurrently
    history_tasks = [_fetch_history(t) for t in tickers]
    spy_task = _fetch_spy_history()
    sector_tasks = [_fetch_sector(t) for t in tickers]

    results = await asyncio.gather(
        *history_tasks,
        spy_task,
        *sector_tasks,
        return_exceptions=True,
    )

    n_tickers = len(tickers)
    history_results = results[:n_tickers]
    spy_hist_raw = results[n_tickers]
    sector_results = results[n_tickers + 1 :]

    # Parse history results
    ticker_hist: dict[str, Any] = {}
    for res in history_results:
        if isinstance(res, Exception):
            continue
        ticker, hist = res
        ticker_hist[ticker] = hist

    # Parse SPY
    spy_returns = None
    if not isinstance(spy_hist_raw, Exception) and spy_hist_raw is not None:
        try:
            spy_ret = spy_hist_raw.pct_change().dropna()
            if len(spy_ret) >= 10:
                spy_returns = spy_ret
        except Exception:
            spy_returns = None

    # Parse sectors
    sector_map: dict[str, str] = {}
    for res in sector_results:
        if isinstance(res, Exception):
            continue
        ticker, sector = res
        sector_map[ticker] = sector

    # ---- Compute per-holding metrics ----

    holdings_risk: list[dict] = []
    portfolio_beta_num = 0.0
    portfolio_beta_den = 0.0
    portfolio_vol_num = 0.0
    portfolio_vol_den = 0.0

    ticker_returns: dict[str, Any] = {}

    for h in holdings:
        ticker = h["ticker"]
        weight = h["_market_value"] / total_equity
        sector = sector_map.get(ticker, "Unknown")

        hist = ticker_hist.get(ticker)
        vol_annual: float | None = None
        beta: float | None = None

        if hist is not None:
            try:
                daily_ret = hist.pct_change().dropna()
                if len(daily_ret) >= 2:
                    ticker_returns[ticker] = daily_ret
                    std_daily = float(daily_ret.std())
                    vol_annual = round(std_daily * math.sqrt(252), 4)

                    # Beta vs SPY
                    if spy_returns is not None:
                        # Align on common dates
                        common_idx = daily_ret.index.intersection(spy_returns.index)
                        if len(common_idx) >= 10:
                            stock_aligned = daily_ret.loc[common_idx]
                            spy_aligned = spy_returns.loc[common_idx]
                            cov = float(stock_aligned.cov(spy_aligned))
                            var_spy = float(spy_aligned.var())
                            if var_spy != 0.0:
                                beta = round(cov / var_spy, 4)
            except Exception:
                pass

        if vol_annual is not None:
            portfolio_vol_num += weight * vol_annual
            portfolio_vol_den += weight

        if beta is not None:
            portfolio_beta_num += weight * beta
            portfolio_beta_den += weight

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

    portfolio_beta = round(portfolio_beta_num / portfolio_beta_den, 4) if portfolio_beta_den > 0 else None
    portfolio_volatility = round(portfolio_vol_num / portfolio_vol_den, 4) if portfolio_vol_den > 0 else None

    # ---- Sector weights ----
    sector_values: dict[str, float] = {}
    for h in holdings:
        ticker = h["ticker"]
        mv = h["_market_value"]
        s = sector_map.get(ticker, "Unknown")
        sector_values[s] = sector_values.get(s, 0.0) + mv

    sector_weights = [
        {"sector": s, "weight_pct": round(mv / total_equity * 100.0, 4)} for s, mv in sector_values.items()
    ]
    sector_weights.sort(key=lambda x: x["weight_pct"], reverse=True)

    # ---- Correlation matrix ----
    correlation: list[dict] = []
    ticker_list = list(ticker_returns.keys())
    for _i, ta in enumerate(ticker_list):
        for _j, tb in enumerate(ticker_list):
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
                    correlation.append(
                        {
                            "ticker_a": ta,
                            "ticker_b": tb,
                            "correlation": round(corr, 3),
                        }
                    )
            except Exception:
                pass

    return {
        "beta": portfolio_beta,
        "volatility": portfolio_volatility,
        "sector_weights": sector_weights,
        "correlation": correlation,
        "holdings_risk": holdings_risk,
    }
