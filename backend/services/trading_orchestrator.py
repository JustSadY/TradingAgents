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

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.execution.base import OrderRequest, OrderResult
from backend.services.execution.factory import get_trader
from backend.services.mock_trading_service import get_or_create_sim_portfolio
from backend.trading_agents.agents.runtime.risk_math import calculate_kelly_size, get_risk_reward_from_plan

_logger = logging.getLogger(__name__)

_SIGNAL_TO_ACTION = {
    "Buy": "BUY",
    "Overweight": "BUY",
    "Sell": "SELL",
    "Underweight": "SELL",
}


def is_actionable(signal: str | None) -> bool:
    return signal in _SIGNAL_TO_ACTION


def _safe_float(raw) -> float | None:
    """``float()`` that folds ``None`` and non-numeric values into ``None``."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _annotations(row) -> dict:
    """Return ``row.chart_annotations`` when it is a dict, else an empty dict."""
    ann = getattr(row, "chart_annotations", None)
    return ann if isinstance(ann, dict) else {}


def _extract_confidence_score(row) -> float | None:
    chart_annotations = getattr(row, "chart_annotations", None)
    if isinstance(chart_annotations, dict):
        trader_prop = chart_annotations.get("trader_proposal")
        if isinstance(trader_prop, dict):
            raw = trader_prop.get("confidence_score")
            if raw is not None:
                return float(raw)

        raw = chart_annotations.get("confidence_score")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            pass

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


def _extract_leverage(row) -> float:
    """Pull the AI's per-stock leverage recommendation, clamped to [1, 10].

    Prefers the structured PortfolioDecision / TraderProposal carried in
    ``chart_annotations``; falls back to a "**Recommended Leverage**: Nx" line
    in the rendered decision text. Defaults to 1.0 (cash) when unspecified.
    """
    ann = _annotations(row)
    candidates: list = [ann.get("recommended_leverage")]
    for nested_key in ("portfolio_decision", "trader_proposal"):
        nested = ann.get(nested_key)
        if isinstance(nested, dict):
            candidates.append(nested.get("recommended_leverage"))

    for raw in candidates:
        value = _safe_float(raw)
        if value is not None and value >= 1.0:
            return min(value, 10.0)

    for text in (getattr(row, "final_decision", "") or "", getattr(row, "trader_plan", "") or ""):
        match = re.search(r"Recommended\s+Leverage\s*[:=]\s*\*?\*?\s*([0-9]+(?:\.[0-9]+)?)\s*x", text, re.IGNORECASE)
        value = _safe_float(match.group(1)) if match else None
        if value is not None and value >= 1.0:
            return min(value, 10.0)
    return 1.0


def _extract_price_level(text: str, label: str, row=None) -> float | None:
    trader_prop = _annotations(row).get("trader_proposal")
    if isinstance(trader_prop, dict):
        key_map = {"Entry Price": "entry_price", "Stop Loss": "stop_loss", "Take Profit": "take_profit_price"}
        struct_key = key_map.get(label)
        if struct_key and trader_prop.get(struct_key):
            return float(trader_prop[struct_key])

    pattern = rf"\*\*{re.escape(label)}\*\*\s*:\s*\$?\s*([0-9]+(?:\.[0-9]+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    value = _safe_float(match.group(1)) if match else None
    return value if (value is not None and value > 0) else None


def _extract_kelly_ceiling_pct(row, *, confidence_score: float | None, current_price: float) -> float | None:
    for key in ("kelly_recommendation_pct", "kelly_position_size_pct", "kelly_pct"):
        parsed = _safe_float(_annotations(row).get(key))
        if parsed is not None and parsed > 0:
            return min(parsed, 100.0)

    final_decision = getattr(row, "final_decision", "") or ""
    match = re.search(
        r"Suggested\s+Maximum\s+Position\s+Size\s*:\s*([0-9]+(?:\.[0-9]+)?)%",
        final_decision,
        flags=re.IGNORECASE,
    )
    parsed = _safe_float(match.group(1)) if match else None
    if parsed is not None and parsed > 0:
        return min(parsed, 100.0)

    trader_plan = getattr(row, "trader_plan", "") or ""
    entry = _extract_price_level(trader_plan, "Entry Price", row=row) or current_price
    stop = _extract_price_level(trader_plan, "Stop Loss", row=row)
    target = _extract_price_level(trader_plan, "Take Profit", row=row)
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
        risk_per_share = max(abs(price - stop_loss), 0.005 * price)
        quantity = risk_usd / risk_per_share
    else:
        quantity = risk_usd / price
    max_alloc_usd = (max_position_size_pct / 100.0) * capital
    max_qty = max_alloc_usd / price
    return min(quantity, max_qty)


async def _existing_long_quantity(db, portfolio_id: int, ticker: str) -> float:
    """Current long quantity held in ``ticker`` (0 if none / short / absent)."""
    from backend.repositories.portfolio import get_holding

    holding = await get_holding(db, portfolio_id, ticker)
    if holding is None or getattr(holding, "side", "long") != "long":
        return 0.0
    return float(holding.quantity)


async def _apply_portfolio_risk_caps(db, *, portfolio, ticker, price, quantity, settings) -> float:
    """Shrink ``quantity`` so the resulting position respects the portfolio's
    single-name concentration and gross-exposure limits. Returns the (possibly
    reduced) quantity; 0 means the order should be skipped."""
    from backend.services.mock_trading_service import get_portfolio_with_live_prices
    from backend.services.portfolio_risk_service import (
        DEFAULT_MAX_CONCENTRATION_PCT,
        DEFAULT_MAX_GROSS_EXPOSURE,
        cap_order_notional,
    )

    try:
        snapshot = await get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)
    except Exception as exc:  # noqa: BLE001 — never block trading on the risk snapshot
        _logger.debug("Risk snapshot failed for %s (allowing order): %s", ticker, exc)
        return quantity

    equity = float(snapshot.get("total_value") or 0.0)
    holdings = snapshot.get("holdings", [])
    existing_gross = sum(float(h.get("market_value") or 0.0) for h in holdings)
    existing_ticker = sum(float(h.get("market_value") or 0.0) for h in holdings if h.get("ticker") == ticker)
    proposed_notional = price * quantity

    assessment = cap_order_notional(
        equity=equity,
        proposed_notional=proposed_notional,
        existing_ticker_notional=existing_ticker,
        existing_gross_notional=existing_gross,
        max_concentration_pct=getattr(settings, "max_concentration_pct", DEFAULT_MAX_CONCENTRATION_PCT),
        max_gross_exposure=getattr(settings, "max_gross_exposure", DEFAULT_MAX_GROSS_EXPOSURE),
    )
    if assessment.capped:
        _logger.info(
            "Risk cap (%s) reduced %s order notional %.2f -> %.2f",
            assessment.reason,
            ticker,
            proposed_notional,
            assessment.allowed_notional,
        )
    return assessment.allowed_notional / price if price > 0 else 0.0


async def place_signal_order(
    db: AsyncSession,
    *,
    ticker: str,
    row,
    settings,
    user=None,
) -> OrderResult | None:
    """Size and place a paper order for ``row``'s signal.

    Returns the ``OrderResult`` (so callers can persist their own order record),
    or ``None`` when the signal is not actionable or no price is available.
    The caller is responsible for committing the transaction.
    """
    action = _SIGNAL_TO_ACTION.get(row.signal)
    if action is None:
        return None
    from backend.repositories.analysis import get_system_settings

    sys_settings = await get_system_settings(db)
    sys_mode = sys_settings.trading_mode if sys_settings else "simulation"
    sys_broker = sys_settings.active_broker if sys_settings else "simulation"

    if sys_broker == "alpaca":
        if not user or not getattr(user, "is_owner", False):
            _logger.warning("Alpaca broker can only be used by the owner user; skipping order execution")
            return None

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
    take_profit = None
    if hasattr(row, "chart_annotations") and row.chart_annotations:
        try:
            if isinstance(row.chart_annotations, str):
                ann = json.loads(row.chart_annotations)
            else:
                ann = row.chart_annotations
            if isinstance(ann, dict):
                stop_loss = ann.get("stop_loss")
                take_profit = ann.get("target_price")
        except Exception as exc:
            _logger.warning("Could not parse chart annotations for SL/TP on analysis %s: %s", row.id, exc)

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
    allow_short = bool(getattr(settings, "allow_short_selling", True))
    existing_long_qty = await _existing_long_quantity(db, portfolio.id, ticker)
    opening_exposure = action == "BUY" or (action == "SELL" and allow_short and existing_long_qty <= 0)
    leverage = _extract_leverage(row) if opening_exposure else 1.0
    if opening_exposure:
        quantity = await _apply_portfolio_risk_caps(
            db, portfolio=portfolio, ticker=ticker, price=price, quantity=quantity, settings=settings
        )
        if quantity <= 0:
            _logger.info("Portfolio risk caps left no room for %s; skipping order", ticker)
            return None

    request = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=quantity,
        reference_price=price,
        ai_signal=row.signal or "",
        ai_reasoning=(row.final_decision or "")[:500],
        leverage=leverage,
        stop_loss=stop_loss if opening_exposure else None,
        take_profit=take_profit if opening_exposure else None,
        allow_short=allow_short,
    )
    result = await trader.place_order(request)
    _logger.info("Order placed: %s %s %s -> %s", action, quantity, ticker, result.status)
    if result.filled_quantity and result.filled_price:
        try:
            from backend.services.notification_service import notify_trade_executed

            await notify_trade_executed(ticker, action, result.filled_quantity, result.filled_price, settings)
        except Exception as exc:
            _logger.debug("trade_executed webhook failed (non-fatal): %s", exc)

    return result
