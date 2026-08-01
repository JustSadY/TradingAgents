from __future__ import annotations

import statistics
from decimal import Decimal

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.money import safe_decimal
from backend.models.order import Order
from backend.models.portfolio import Portfolio
from backend.models.user import User
from backend.repositories.portfolio import get_simulation_portfolio

_CLOSING_STATUSES = frozenset({"FILLED", "STOP_LOSS", "TAKE_PROFIT", "LIQUIDATED"})

def _is_closing_order(order: Order) -> bool:
    """Whether an order represents a completed position exit.

    ``action`` alone is insufficient: a SELL opens a short while a BUY closes
    it.  Auto-closes retain the same action/side pairing but use a terminal
    status such as ``STOP_LOSS`` instead of ``FILLED``.
    """
    if order.status not in _CLOSING_STATUSES:
        return False
    side = (order.side or "long").lower()
    action = (order.action or "").upper()
    return (side == "long" and action == "SELL") or (side == "short" and action == "BUY")

def _closing_orders(orders: list[Order]) -> list[Order]:
    """Keep only terminal orders that actually close a long or short."""
    return [order for order in orders if _is_closing_order(order)]

def _equity_max_drawdown_pct(initial_capital: Decimal, orders: list[Order]) -> float | None:
    """Return the negative peak-to-trough drawdown for realized trade equity.

    This deliberately starts at deposited capital.  A P&L-only curve has no
    meaningful denominator around zero and wildly overstates normal reversals.
    """
    equity = safe_decimal(initial_capital)
    if equity <= 0:
        return None

    peak = equity
    max_drawdown = Decimal("0.0")
    for order in orders:
        equity += safe_decimal(order.realized_pnl)
        if equity > peak:
            peak = equity
        elif peak > 0:
            drawdown = (peak - equity) / peak * Decimal("100")
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    return -float(max_drawdown)

def _closing_cost_basis(order: Order, pnl: Decimal) -> Decimal:
    """Derive all-in entry capital from a closing order's fill and P&L.

    Simulation closing orders store exit notional, exit-leg commission, and
    the pro-rata opening commission carried by the holding.  A long has
    ``pnl = exit - entry - entry_commission - exit_commission``; a short has
    ``pnl = entry - exit - entry_commission - exit_commission``.  Return
    percentages therefore use actual capital committed, not a pre-fee value.
    """
    exit_notional = safe_decimal(order.total_value)
    exit_commission = safe_decimal(order.commission)
    entry_commission = safe_decimal(getattr(order, "entry_commission", None))
    if (order.side or "long").lower() == "short":
        entry_notional = exit_notional + pnl + entry_commission + exit_commission
    else:
        entry_notional = exit_notional - pnl - entry_commission - exit_commission
    return entry_notional + entry_commission

async def get_portfolio_stats(db: AsyncSession, user: User) -> dict:
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

    result = await db.execute(
        select(Order)
        .where(
            Order.portfolio_id == portfolio.id,
            Order.status.in_(_CLOSING_STATUSES),
        )
        .order_by(asc(Order.created_at))
    )
    orders: list[Order] = _closing_orders(list(result.scalars().all()))

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
    win_rate = winning_trades / total_trades * 100

    returns_pct: list[float] = []
    trade_data: list[dict] = []

    for o in orders:
        pnl = safe_decimal(o.realized_pnl)
        cost_basis = _closing_cost_basis(o, pnl)
        if abs(cost_basis) > Decimal("1e-9"):
            ret_pct = float(pnl / cost_basis * Decimal("100"))
            returns_pct.append(ret_pct)
            trade_data.append(
                {
                    "ticker": o.ticker,
                    "pnl_pct": ret_pct,
                    "date": o.created_at.isoformat() if o.created_at else None,
                    "pnl": float(pnl),
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

    total_realized_pnl = float(sum(safe_decimal(o.realized_pnl) for o in orders))

    sharpe_ratio: float | None = None
    if len(returns_pct) >= 2:
        mean_r = statistics.mean(returns_pct)
        std_r = statistics.stdev(returns_pct)
        if abs(std_r) > 1e-9:
            sharpe_ratio = round(mean_r / std_r, 3)
        else:
            sharpe_ratio = None

    max_drawdown_pct = _equity_max_drawdown_pct(safe_decimal(portfolio.initial_capital), orders)

    ticker_map: dict[str, dict] = {}
    for o in orders:
        t = o.ticker
        if t not in ticker_map:
            ticker_map[t] = {"ticker": t, "trades": 0, "wins": 0, "total_pnl": Decimal("0")}
        pnl = safe_decimal(o.realized_pnl)
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
                "total_pnl": float(entry["total_pnl"]),
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
