import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.services.portfolio_service import get_active_holdings, get_user_simulation_portfolio

router = APIRouter(prefix="/api/trading", tags=["trading"])


@router.get("/correlation")
async def get_correlation(
    period: str = Query(default="90d", description="Data period: 30d, 90d, 180d, 1y"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compute pairwise correlation matrix for the user's current holdings."""
    valid_periods = {"30d", "90d", "180d", "1y"}
    if period not in valid_periods:
        period = "90d"

    portfolio = await get_user_simulation_portfolio(db, current_user.id)

    if portfolio is None:
        return {"tickers": [], "matrix": [], "avg_correlation": None, "warning": "No portfolio found"}

    holdings = await get_active_holdings(db, portfolio.id)

    tickers = [h.ticker for h in holdings]

    if len(tickers) < 2:
        return {
            "tickers": tickers,
            "matrix": [],
            "avg_correlation": None,
            "warning": "Need at least 2 holdings",
        }

    def _download_and_correlate():
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

    loop = asyncio.get_event_loop()
    corr_df, available_tickers = await loop.run_in_executor(None, _download_and_correlate)

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
