"""Shared logic for turning an analysis signal into a paper-trade order.

Both the manual analysis flow (``analysis_service``) and the scheduled
watchlist scan (``cron_service``) need to: look at a finished analysis row,
decide whether the signal is actionable, size a position against the user's
simulation portfolio cash, and place the order through the configured trader.

That logic used to be copy-pasted in three places (with a hardcoded $100k
capital in two of them). It now lives here.
"""

from __future__ import annotations

import json
import logging
import math
import re
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import is_live_trading_enabled
from backend.core.constants import SIGNAL_TO_ACTION
from backend.core.money import safe_decimal
from backend.services.execution.base import OrderRequest, OrderResult
from backend.services.execution.factory import get_trader
from backend.services.mock_trading_service import get_or_create_sim_portfolio
from backend.trading_agents.agents.runtime.risk_math import calculate_kelly_size, get_risk_reward_from_plan

_logger = logging.getLogger(__name__)


def is_actionable(signal: str | None) -> bool:
    return signal in SIGNAL_TO_ACTION


def _record_skip(reason: str) -> None:
    """Best-effort Prometheus counter bump for a guardrail-skipped auto-order."""
    try:
        from backend.core.metrics import AUTO_ORDER_SKIPPED

        AUTO_ORDER_SKIPPED.labels(reason=reason).inc()
    except Exception:  # noqa: BLE001 — metrics are optional, never block trading
        _logger.debug("Metrics skip counter unavailable (non-fatal)")


def _safe_float(raw) -> float | None:
    """``float()`` that folds ``None`` and non-numeric values into ``None``."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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
        if parsed is not None and parsed >= 0:
            return min(parsed, 100.0)

    final_decision = getattr(row, "final_decision", "") or ""
    match = re.search(
        r"Suggested\s+Maximum\s+Position\s+Size\s*:\s*([0-9]+(?:\.[0-9]+)?)%",
        final_decision,
        flags=re.IGNORECASE,
    )
    parsed = _safe_float(match.group(1)) if match else None
    if parsed is not None and parsed >= 0:
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
    """Position size from risk-per-trade sizing, capped by max allocation.

    Computed in Decimal (converting back to float at the return boundary) so
    this sizing formula's own chain of multiplies/divides doesn't accumulate
    binary-float rounding error. The function still takes/returns plain
    floats: its caller chain (``_apply_portfolio_risk_caps`` and onward) is
    float-based, and converting that whole chain is a larger, separate
    change (see docs/architecture — the Decimal boundary is at order
    execution in mock_trading_service.py, which re-quantizes from a string
    regardless of what this function returns).
    """
    risk_pct_d = Decimal(str(risk_per_trade_pct))
    capital_d = Decimal(str(capital))
    price_d = Decimal(str(price))
    kelly_d = Decimal(str(max(0.0, min(1.0, kelly_multiplier))))

    risk_usd = (risk_pct_d / Decimal(100)) * capital_d
    risk_usd *= kelly_d
    if stop_loss and stop_loss > 0 and stop_loss != price:
        stop_loss_d = Decimal(str(stop_loss))
        risk_per_share = max(abs(price_d - stop_loss_d), Decimal("0.005") * price_d)
        quantity = risk_usd / risk_per_share
    else:
        quantity = risk_usd / price_d
    max_alloc_usd = (Decimal(str(max_position_size_pct)) / Decimal(100)) * capital_d
    max_qty = max_alloc_usd / price_d
    return float(min(quantity, max_qty))


def _classify_order_intent(action: str, existing_side: str | None, allow_short: bool) -> str | None:
    """Classify an auto-order without confusing a close for new exposure.

    Returns ``None`` when a SELL would open a new short while short selling is
    disabled.  Existing positions can always be closed after the setting is
    disabled, which is essential for risk reduction.
    """
    side = (existing_side or "").lower()
    if action == "BUY":
        return "close_short" if side == "short" else "open_long"
    if action == "SELL":
        if side == "long":
            return "close_long"
        return "open_short" if allow_short else None
    return None


def _directional_exit_levels(
    side: str,
    entry_price: float,
    raw_stop_loss,
    raw_take_profit,
) -> tuple[float | None, float | None]:
    """Keep only stop/target levels valid for ``side`` at ``entry_price``."""
    stop_loss = _safe_float(raw_stop_loss)
    take_profit = _safe_float(raw_take_profit)
    if side == "short":
        return (
            stop_loss if stop_loss is not None and stop_loss > entry_price else None,
            take_profit if take_profit is not None and take_profit < entry_price else None,
        )
    return (
        stop_loss if stop_loss is not None and stop_loss < entry_price else None,
        take_profit if take_profit is not None and take_profit > entry_price else None,
    )


def _default_exit_levels(side: str, entry_price: float) -> tuple[float, float]:
    """Conservative fallback exits used when strict stop-loss mode is off."""
    if side == "short":
        return entry_price * 1.05, entry_price * 0.90
    return entry_price * 0.95, entry_price * 1.10


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
        snapshot = await get_portfolio_with_live_prices(db, portfolio_id=portfolio.id, read_only=True)
    except Exception as exc:  # noqa: BLE001 — risk data unavailable must not open exposure
        _logger.warning("Risk snapshot failed for %s; skipping new order: %s", ticker, exc)
        _record_skip("risk_snapshot_unavailable")
        return 0.0

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("holdings", []), list):
        _logger.warning("Risk snapshot for %s has an invalid shape; skipping new order", ticker)
        _record_skip("risk_snapshot_invalid")
        return 0.0

    equity = _safe_float(snapshot.get("total_value"))
    if equity is None or equity <= 0:
        _logger.warning(
            "Risk snapshot for %s has invalid equity %r; skipping new order", ticker, snapshot.get("total_value")
        )
        _record_skip("risk_snapshot_invalid")
        return 0.0

    holdings = snapshot["holdings"]
    try:
        holding_values = []
        for holding in holdings:
            if not isinstance(holding, dict):
                raise ValueError("holding is not an object")
            market_value = _safe_float(holding.get("market_value"))
            if market_value is None or market_value < 0:
                raise ValueError(f"invalid holding market value {holding.get('market_value')!r}")
            holding_values.append((holding, market_value))
    except (TypeError, ValueError) as exc:
        _logger.warning("Risk snapshot holdings are invalid for %s; skipping new order: %s", ticker, exc)
        _record_skip("risk_snapshot_invalid")
        return 0.0

    existing_gross = sum(value for _holding, value in holding_values)
    existing_ticker = sum(value for holding, value in holding_values if holding.get("ticker") == ticker)
    proposed_notional = price * quantity

    # Correlation-aware sizing is opt-in: it fetches price history for every
    # holding, so we only pay that cost when the user enables it.
    correlated = 0.0
    if getattr(settings, "correlation_risk_enabled", False):
        try:
            from backend.services.risk_dashboard_service import correlated_notional

            correlated = await correlated_notional(ticker, holdings)
        except Exception as exc:  # noqa: BLE001 — never block trading on the correlation calc
            _logger.warning("Correlation risk calc failed for %s (ignoring): %s", ticker, exc)
            correlated = 0.0

    max_concentration_pct = _safe_float(getattr(settings, "max_concentration_pct", None))
    max_gross_exposure = _safe_float(getattr(settings, "max_gross_exposure", None))
    try:
        assessment = cap_order_notional(
            equity=equity,
            proposed_notional=proposed_notional,
            existing_ticker_notional=existing_ticker,
            existing_gross_notional=existing_gross,
            max_concentration_pct=max_concentration_pct
            if max_concentration_pct is not None and max_concentration_pct > 0
            else DEFAULT_MAX_CONCENTRATION_PCT,
            max_gross_exposure=max_gross_exposure
            if max_gross_exposure is not None and max_gross_exposure > 0
            else DEFAULT_MAX_GROSS_EXPOSURE,
            correlated_notional=correlated,
        )
    except Exception as exc:  # noqa: BLE001 — malformed risk inputs must not open exposure
        _logger.warning("Risk cap calculation failed for %s; skipping new order: %s", ticker, exc)
        _record_skip("risk_cap_failed")
        return 0.0
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
    action = SIGNAL_TO_ACTION.get(row.signal)
    if action is None:
        return None

    # Quality gate (opt-in): don't auto-trade low-confidence runs — the ones with
    # degraded/missing analyst reports or an automated-fallback decision, which are
    # the most likely to be noise. The analysis is still saved; only the auto-order
    # is skipped.
    if getattr(settings, "quality_gate_enabled", False):
        quality = getattr(row, "quality", None)
        if isinstance(quality, dict) and quality.get("confidence") == "low":
            _logger.info(
                "Quality gate: skipping auto-order for %s (low-confidence run, score=%s)",
                ticker,
                quality.get("score"),
            )
            _record_skip("quality_gate")
            return None

    from backend.repositories.system_settings import get_system_settings

    sys_settings = await get_system_settings(db)
    sys_mode = sys_settings.trading_mode if sys_settings else "simulation"
    sys_broker = sys_settings.active_broker if sys_settings else "simulation"

    if sys_mode not in {"simulation", "live"} or sys_broker not in {"simulation", "alpaca"}:
        _logger.error(
            "Invalid server trading configuration (mode=%s, broker=%s); skipping order execution",
            sys_mode,
            sys_broker,
        )
        _record_skip("invalid_trading_configuration")
        return None

    if sys_mode == "live":
        if sys_broker != "alpaca":
            _logger.error("Live mode requires the Alpaca broker; skipping order execution")
            _record_skip("invalid_live_broker")
            return None
        if not is_live_trading_enabled():
            _logger.warning("Live order skipped because ENABLE_LIVE_TRADING is disabled")
            _record_skip("live_trading_disabled")
            return None

    if sys_broker == "alpaca":
        if not user or not getattr(user, "is_owner", False):
            _logger.warning("Alpaca broker can only be used by the owner user; skipping order execution")
            return None

    portfolio = await get_or_create_sim_portfolio(db, user=user)

    # Work out whether the signal reduces risk or opens/adds exposure before
    # applying any breaker or sizing rule.  A BUY against an existing short and
    # a SELL against an existing long must close the full held quantity.
    from backend.repositories.portfolio import get_holding

    holding = await get_holding(db, portfolio.id, ticker)
    allow_short = bool(getattr(settings, "allow_short_selling", False))
    intent = _classify_order_intent(action, getattr(holding, "side", None), allow_short)
    if intent is None:
        _logger.info("Short selling is disabled; skipping new short signal for %s", ticker)
        _record_skip("short_disabled")
        return None
    opening_exposure = intent in {"open_long", "open_short"}
    position_side = "short" if intent in {"open_short", "close_short"} else "long"

    # Drawdown circuit breaker (opt-in): halt new auto-orders once the portfolio
    # has fallen more than the configured % below its starting capital. Existing
    # positions are untouched — this only blocks opening/adding new exposure.
    if opening_exposure and getattr(settings, "drawdown_breaker_enabled", False):
        try:
            initial_capital = _safe_float(portfolio.initial_capital)
            max_drawdown_pct = _safe_float(getattr(settings, "max_portfolio_drawdown_pct", 20.0))
            if initial_capital is None or initial_capital <= 0 or max_drawdown_pct is None or max_drawdown_pct < 0:
                raise ValueError("invalid portfolio capital or drawdown threshold")

            from backend.services.mock_trading_service import get_portfolio_with_live_prices

            snapshot = await get_portfolio_with_live_prices(db, portfolio_id=portfolio.id, read_only=True)
            current_equity = _safe_float(snapshot.get("total_value")) if isinstance(snapshot, dict) else None
            if current_equity is None:
                raise ValueError("snapshot has no finite total_value")
            drawdown_pct = max(0.0, (initial_capital - current_equity) / initial_capital * 100.0)
            if drawdown_pct > max_drawdown_pct:
                _logger.warning(
                    "Drawdown circuit breaker: skipping auto-order for %s (drawdown %.1f%% > %.1f%%)",
                    ticker,
                    drawdown_pct,
                    max_drawdown_pct,
                )
                _record_skip("drawdown_breaker")
                return None
        except Exception as exc:  # noqa: BLE001 — unsafe breaker state must not open exposure
            _logger.warning("Drawdown breaker check failed for %s; skipping new order: %s", ticker, exc)
            _record_skip("drawdown_snapshot_unavailable")
            return None

    trader = get_trader(
        mode=sys_mode,
        broker=sys_broker,
        portfolio_id=portfolio.id,
        initial_capital=float(safe_decimal(portfolio.initial_capital)),
        db=db,
    )
    price = float(safe_decimal(await trader.get_current_price(ticker)))
    if price <= 0:
        _logger.warning("No price available for %s; skipping order execution", ticker)
        return None

    raw_stop_loss = None
    raw_take_profit = None
    if hasattr(row, "chart_annotations") and row.chart_annotations:
        try:
            if isinstance(row.chart_annotations, str):
                ann = json.loads(row.chart_annotations)
            else:
                ann = row.chart_annotations
            if isinstance(ann, dict):
                raw_stop_loss = ann.get("stop_loss")
                raw_take_profit = ann.get("target_price")
        except Exception as exc:
            _logger.warning("Could not parse chart annotations for SL/TP on analysis %s: %s", row.id, exc)

    if opening_exposure:
        stop_loss, take_profit = _directional_exit_levels(position_side, price, raw_stop_loss, raw_take_profit)
        strict_stop_loss_mode = bool(getattr(settings, "strict_stop_loss_mode", False))
        if strict_stop_loss_mode and stop_loss is None:
            _logger.warning(
                "Strict stop-loss mode enabled and no valid %s stop-loss found for %s; skipping order execution",
                position_side,
                ticker,
            )
            _record_skip("invalid_stop_loss")
            return None
        if not strict_stop_loss_mode:
            default_stop, default_target = _default_exit_levels(position_side, price)
            stop_loss = stop_loss if stop_loss is not None else default_stop
            take_profit = take_profit if take_profit is not None else default_target

        available_cash = safe_decimal(portfolio.cash_available)
        if available_cash <= 0:
            _logger.info("No available cash for a new %s position in %s; skipping order", position_side, ticker)
            _record_skip("cash_unavailable")
            return None
        capital = float(available_cash)
        base_risk_pct = _safe_float(getattr(settings, "max_risk_per_trade_pct", None))
        max_position_size_pct = _safe_float(getattr(settings, "max_position_size_pct", None))
        if base_risk_pct is None or base_risk_pct <= 0 or max_position_size_pct is None or max_position_size_pct <= 0:
            _logger.warning("Invalid risk sizing configuration; skipping auto-order for %s", ticker)
            _record_skip("invalid_risk_settings")
            return None

        # Kelly is a cap on position allocation, not a risk-per-trade
        # percentage.  Keeping the units separate prevents a 20% Kelly size
        # from being compared to, and silently neutralised by, a 2% risk cap.
        confidence_score = _extract_confidence_score(row)
        kelly_ceiling_pct = _extract_kelly_ceiling_pct(
            row,
            confidence_score=confidence_score,
            current_price=price,
        )
        if kelly_ceiling_pct is not None:
            max_position_size_pct = min(max_position_size_pct, kelly_ceiling_pct)

        quantity = _position_quantity(
            base_risk_pct,
            capital,
            price,
            stop_loss=stop_loss,
            max_position_size_pct=max_position_size_pct,
        )
        if quantity <= 0:
            _logger.info("Risk sizing left no room for %s; skipping order", ticker)
            _record_skip("position_size_zero")
            return None
        quantity = await _apply_portfolio_risk_caps(
            db, portfolio=portfolio, ticker=ticker, price=price, quantity=quantity, settings=settings
        )
        if quantity <= 0:
            _logger.info("Portfolio risk caps left no room for %s; skipping order", ticker)
            return None
        leverage = _extract_leverage(row)
    else:
        # Exit exactly what is held.  Never re-run a risk sizing formula for a
        # close: it can produce zero or an amount larger than the position.
        if holding is None:
            _logger.warning("No existing %s position found to close for %s", position_side, ticker)
            return None
        quantity = float(safe_decimal(holding.quantity))
        if quantity <= 0:
            _logger.warning("Existing %s position for %s has no quantity to close", position_side, ticker)
            return None
        stop_loss = None
        take_profit = None
        leverage = 1.0

    request = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=safe_decimal(quantity),
        reference_price=safe_decimal(price),
        ai_signal=row.signal or "",
        ai_reasoning=(row.final_decision or "")[:500],
        leverage=leverage,
        stop_loss=safe_decimal(stop_loss) if opening_exposure and stop_loss else None,
        take_profit=safe_decimal(take_profit) if opening_exposure and take_profit else None,
        allow_short=allow_short,
    )
    result = await trader.place_order(request)
    _logger.info("Order placed: %s %s %s -> %s", action, quantity, ticker, result.status)
    if result.filled_quantity and result.filled_price:
        try:
            from backend.services.notification_service import notify_trade_executed

            await notify_trade_executed(ticker, action, result.filled_quantity, result.filled_price, settings)
        except Exception as exc:
            _logger.warning("trade_executed webhook failed (non-fatal): %s", exc)

    return result
