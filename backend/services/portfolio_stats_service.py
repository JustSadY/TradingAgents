from __future__ import annotations

import statistics
from decimal import Decimal

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Portfolio
from backend.models.user import User
from backend.repositories.portfolio import get_simulation_portfolio


async def get_portfolio_stats(db: AsyncSession, user: User) -> dict:
    """Calculate trading statistics from closed positions (SELL orders with non-zero realized_pnl)."""

    portfolio: Portfolio | None = await get_simulation_portfolio(db, user_id=user.id)

    if portfolio is None:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": None,
            "best_trade": None,
            "worst_trade": None,
            "total_realized_pnl": 0.0,
            "sharpe_ratio": None,
            "max_drawdown_pct": None,
            "by_ticker": [],
        }

    # Query all SELL FILLED orders for this portfolio ordered by created_at asc
    result = await db.execute(
        select(Order)
        .where(
            Order.portfolio_id == portfolio.id,
            Order.status == "FILLED",
            Order.action == "SELL",
        )
        .order_by(asc(Order.created_at))
    )
    orders: list[Order] = list(result.scalars().all())

    total_trades = len(orders)

    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": None,
            "best_trade": None,
            "worst_trade": None,
            "total_realized_pnl": 0.0,
            "sharpe_ratio": None,
            "max_drawdown_pct": None,
            "by_ticker": [],
        }

    winning_trades = sum(1 for o in orders if (o.realized_pnl or Decimal("0")) > 0)
    win_rate = winning_trades / total_trades

    # Per-trade return percentages: realized_pnl / cost_basis * 100
    # cost_basis = total_value - realized_pnl  (what was spent to acquire)
    returns_pct: list[float] = []
    trade_data: list[dict] = []

    for o in orders:
        pnl = float(o.realized_pnl or Decimal("0"))
        tv = float(o.total_value or Decimal("0"))
        cost_basis = tv - pnl
        if abs(cost_basis) > 1e-9:
            ret_pct = pnl / cost_basis * 100.0
            returns_pct.append(ret_pct)
            trade_data.append(
                {
                    "ticker": o.ticker,
                    "pnl_pct": ret_pct,
                    "date": o.created_at.isoformat() if o.created_at else None,
                    "pnl": pnl,
                }
            )

    avg_return_pct: float | None = statistics.mean(returns_pct) if returns_pct else None

    best_trade: dict | None = None
    worst_trade: dict | None = None
    if trade_data:
        best = max(trade_data, key=lambda x: x["pnl_pct"])
        worst = min(trade_data, key=lambda x: x["pnl_pct"])
        best_trade = {"ticker": best["ticker"], "pnl_pct": best["pnl_pct"], "date": best["date"]}
        worst_trade = {"ticker": worst["ticker"], "pnl_pct": worst["pnl_pct"], "date": worst["date"]}

    total_realized_pnl = float(sum(o.realized_pnl or Decimal("0") for o in orders))

    # Sharpe ratio
    sharpe_ratio: float | None = None
    if len(returns_pct) >= 2:
        mean_r = statistics.mean(returns_pct)
        std_r = statistics.stdev(returns_pct)  # ddof=1 by default
        if abs(std_r) > 1e-9:
            sharpe_ratio = round(mean_r / std_r, 3)
        else:
            sharpe_ratio = None

    # Max drawdown on cumulative realized_pnl over time
    max_drawdown_pct: float | None = None
    if total_trades >= 2:
        pnl_values = [float(o.realized_pnl or Decimal("0")) for o in orders]
        cumulative = []
        running = 0.0
        for p in pnl_values:
            running += p
            cumulative.append(running)

        peak = cumulative[0]
        max_dd = 0.0
        for val in cumulative[1:]:
            if val > peak:
                peak = val
            elif abs(peak) > 1e-9:
                dd = (peak - val) / abs(peak) * 100.0
                if dd > max_dd:
                    max_dd = dd

        # Return as negative number (or 0 if no drawdown)
        max_drawdown_pct = -max_dd if max_dd > 0.0 else 0.0

    # By-ticker breakdown
    ticker_map: dict[str, dict] = {}
    for o in orders:
        t = o.ticker
        if t not in ticker_map:
            ticker_map[t] = {"ticker": t, "trades": 0, "wins": 0, "total_pnl": 0.0}
        pnl = float(o.realized_pnl or Decimal("0"))
        ticker_map[t]["trades"] += 1
        ticker_map[t]["total_pnl"] += pnl
        if pnl > 0:
            ticker_map[t]["wins"] += 1

    by_ticker = []
    for entry in ticker_map.values():
        win_rate_ticker = (entry["wins"] / entry["trades"] * 100) if entry["trades"] > 0 else 0.0
        by_ticker.append(
            {
                "ticker": entry["ticker"],
                "trades": entry["trades"],
                "wins": entry["wins"],
                "win_rate": round(win_rate_ticker, 1),
                "total_pnl": entry["total_pnl"],
            }
        )
    by_ticker.sort(key=lambda x: x["total_pnl"], reverse=True)

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "avg_return_pct": avg_return_pct,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "total_realized_pnl": total_realized_pnl,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "by_ticker": by_ticker,
    }
