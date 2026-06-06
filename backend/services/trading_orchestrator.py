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
import re
from typing import Optional

from backend.trading_agents.agents.runtime.risk_math import calculate_kelly_size, get_risk_reward_from_plan

from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.execution.base import OrderRequest, OrderResult
from backend.services.mock_trading_service import get_or_create_sim_portfolio
from backend.services.execution.factory import get_trader

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


def _extract_confidence_score(row) -> float | None:
    chart_annotations = getattr(row, "chart_annotations", None)
    if isinstance(chart_annotations, dict):
        raw = chart_annotations.get("confidence_score")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    confidence_text_sources = [
        getattr(row, "trader_plan", None) or "",
        getattr(row, "final_decision", None) or "",
    ]
    for text in confidence_text_sources:
        match = re.search(r"confidence\s*score\s*[:=]\s*([0-9]*\.?[0-9]+)", text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            parsed = float(match.group(1))
        except ValueError:
            continue
        if parsed > 1.0:
            parsed = parsed / 100.0
        return max(0.0, min(1.0, parsed))
    return None


def _extract_price_level(text: str, label: str) -> float | None:
    pattern = rf"\*\*{re.escape(label)}\*\*\s*:\s*\$?\s*([0-9]+(?:\.[0-9]+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def _extract_kelly_ceiling_pct(row, *, confidence_score: float | None, current_price: float) -> float | None:
    chart_annotations = getattr(row, "chart_annotations", None)
    if isinstance(chart_annotations, dict):
        for key in ("kelly_recommendation_pct", "kelly_position_size_pct", "kelly_pct"):
            raw = chart_annotations.get(key)
            if raw is None:
                continue
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return min(parsed, 100.0)

    final_decision = getattr(row, "final_decision", "") or ""
    match = re.search(
        r"Suggested\s+Maximum\s+Position\s+Size\s*:\s*([0-9]+(?:\.[0-9]+)?)%",
        final_decision,
        flags=re.IGNORECASE,
    )
    if match:
        try:
            parsed = float(match.group(1))
        except ValueError:
            parsed = None
        if parsed and parsed > 0:
            return min(parsed, 100.0)

    trader_plan = getattr(row, "trader_plan", "") or ""
    entry = _extract_price_level(trader_plan, "Entry Price") or current_price
    stop = _extract_price_level(trader_plan, "Stop Loss")
    target = _extract_price_level(trader_plan, "Take Profit")
    if confidence_score is None or stop is None or target is None:
        return None
    rr = get_risk_reward_from_plan(target, stop, entry)
    kelly_size = calculate_kelly_size(confidence_score, rr)
    return max(0.0, min(kelly_size * 100.0, 100.0))


def _position_quantity(
    risk_per_trade_pct: float,
    capital: float,
    price: float,
    stop_loss: float | None = None,
    max_position_size_pct: float = 10.0,
    kelly_multiplier: float = 1.0,
) -> float:
    risk_usd = (risk_per_trade_pct / 100.0) * capital
    risk_usd *= max(0.0, min(1.0, kelly_multiplier))
    if stop_loss and stop_loss > 0 and stop_loss != price:
        risk_per_share = abs(price - stop_loss)
        quantity = risk_usd / risk_per_share
    else:
        quantity = risk_usd / price
    max_alloc_usd = (max_position_size_pct / 100.0) * capital
    max_qty = max_alloc_usd / price
    return min(quantity, max_qty)


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

    # Retrieve system settings to verify active broker mode
    from backend.repositories.analysis import get_system_settings
    sys_settings = await get_system_settings(db)
    sys_mode = sys_settings.trading_mode if sys_settings else "simulation"
    sys_broker = sys_settings.active_broker if sys_settings else "simulation"

    portfolio = await get_or_create_sim_portfolio(db, user=user)
    trader = get_trader(
        mode=sys_mode,
        broker=sys_broker,
        portfolio_id=portfolio.id,
        initial_capital=float(portfolio.initial_capital),
        db=db,
    )
    price = await trader.get_current_price(ticker) or 0.0
    if price <= 0:
        _logger.warning("No price available for %s; skipping order execution", ticker)
        return None

    capital = float(portfolio.cash_available) if portfolio.cash_available > 0 else float(portfolio.initial_capital)
    
    import json
    stop_loss = None
    if hasattr(row, "chart_annotations") and row.chart_annotations:
        try:
            if isinstance(row.chart_annotations, str):
                ann = json.loads(row.chart_annotations)
            else:
                ann = row.chart_annotations
            if isinstance(ann, dict):
                stop_loss = ann.get("stop_loss")
        except Exception:
            pass

    max_position_size_pct = getattr(settings, "max_position_size_pct", 10.0)
    confidence_score = _extract_confidence_score(row)
    kelly_ceiling_pct = _extract_kelly_ceiling_pct(
        row,
        confidence_score=confidence_score,
        current_price=price,
    )
    base_risk_pct = float(settings.max_risk_per_trade_pct)
    effective_risk_pct = base_risk_pct
    if kelly_ceiling_pct is not None:
        effective_risk_pct = min(base_risk_pct, kelly_ceiling_pct)
    kelly_multiplier = (effective_risk_pct / base_risk_pct) if base_risk_pct > 0 else 0.0
    strict_stop_loss_mode = getattr(settings, "strict_stop_loss_mode", False)
    if strict_stop_loss_mode and (stop_loss is None or stop_loss <= 0 or stop_loss == price):
        _logger.warning(
            "Strict stop-loss mode enabled and no valid stop-loss found for %s; skipping order execution",
            ticker,
        )
        return None
    quantity = _position_quantity(
        base_risk_pct,
        capital,
        price,
        stop_loss=stop_loss,
        max_position_size_pct=max_position_size_pct,
        kelly_multiplier=kelly_multiplier,
    )
    request = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=quantity,
        reference_price=price,
        ai_signal=row.signal or "",
        ai_reasoning=(row.final_decision or "")[:500],
    )
    result = await trader.place_order(request)
    _logger.info("Order placed: %s %s %s -> %s", action, quantity, ticker, result.status)
    return result
