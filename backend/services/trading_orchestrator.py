"""Shared logic for turning an analysis signal into a paper-trade order.

Both the manual analysis flow (``analysis_service``) and the scheduled
watchlist scan (``cron_service``) need to: look at a finished analysis row,
decide whether the signal is actionable, size a position against the user's
simulation portfolio cash, and place the order through the configured trader.

That logic used to be copy-pasted in three places (with a hardcoded $100k
capital in two of them). It now lives here.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.execution.base import OrderRequest, OrderResult

_logger = logging.getLogger(__name__)

# Map an analysis signal to a concrete order side. Unlisted signals (e.g. "Hold")
# are intentionally non-actionable.
_SIGNAL_TO_ACTION = {
    "Buy": "BUY",
    "Overweight": "BUY",
    "Sell": "SELL",
    "Underweight": "SELL",
}


def is_actionable(signal: Optional[str]) -> bool:
    return signal in _SIGNAL_TO_ACTION


def _position_quantity(risk_per_trade_pct: float, capital: float, price: float) -> float:
    """Risk-budgeted position size: a fixed fraction of deployable capital."""
    return (risk_per_trade_pct / 100.0 * capital) / price


async def place_signal_order(
    db: AsyncSession,
    *,
    ticker: str,
    row,
    settings,
    user=None,
) -> Optional[OrderResult]:
    """Size and place a paper order for ``row``'s signal.

    Returns the ``OrderResult`` (so callers can persist their own order record),
    or ``None`` when the signal is not actionable or no price is available.
    The caller is responsible for committing the transaction.
    """
    action = _SIGNAL_TO_ACTION.get(row.signal)
    if action is None:
        return None

    from backend.models.system_settings import SystemSettings
    from sqlalchemy import select
    sys_settings = (await db.execute(
        select(SystemSettings).where(SystemSettings.id == 1)
    )).scalar_one_or_none()
    sys_mode = sys_settings.trading_mode if sys_settings else "simulation"
    sys_broker = sys_settings.active_broker if sys_settings else "simulation"

    portfolio = await get_or_create_sim_portfolio(db, user=user)
    trader = get_trader(
        mode=sys_mode,
        broker=sys_broker,
        portfolio_id=portfolio.id,
        initial_capital=portfolio.initial_capital,
        db=None,
    )
    price = trader.get_current_price(ticker) or 0.0
    if price <= 0:
        _logger.warning("No price available for %s; skipping order execution", ticker)
        return None

    capital = portfolio.cash_available if portfolio.cash_available > 0 else portfolio.initial_capital
    quantity = _position_quantity(settings.max_risk_per_trade_pct, capital, price)
    request = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=quantity,
        reference_price=price,
        ai_signal=row.signal or "",
        ai_reasoning=(row.final_decision or "")[:500],
    )
    result = trader.place_order(request)
    _logger.info("Order placed: %s %s %s -> %s", action, quantity, ticker, result.status)
    return result
