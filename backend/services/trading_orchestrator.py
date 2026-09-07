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
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import is_live_trading_enabled
from backend.core.constants import SIGNAL_TO_ACTION
from backend.core.money import safe_decimal
from backend.repositories.trading_execution import (
    apply_broker_account_balances as _repo_apply_broker_account_balances,
)
from backend.repositories.trading_execution import (
    get_or_create_broker_audit_portfolio as _repo_get_or_create_broker_audit_portfolio,
)
from backend.repositories.trading_execution import persist_broker_order as _repo_persist_broker_order
from backend.services.execution.base import OrderRequest, OrderResult
from backend.services.execution.factory import get_trader
from backend.services.mock_trading_service import get_or_create_sim_portfolio

_logger = logging.getLogger(__name__)


def auto_execute_signals_enabled(settings) -> bool:
    """Return whether the user deliberately opted into AI signal execution."""
    return bool(settings.auto_execute_signals)


def _record_skip(reason: str) -> None:
    """Best-effort Prometheus counter bump for a guardrail-skipped auto-order."""
    try:
        from backend.core.metrics import AUTO_ORDER_SKIPPED

        AUTO_ORDER_SKIPPED.labels(reason=reason).inc()
    except Exception:  # noqa: BLE001 — metrics are optional, never block trading
        _logger.debug("Metrics skip counter unavailable (non-fatal)")


def _skipped_order(
    *,
    reason_code: str,
    message: str,
    include_skip_result: bool,
) -> OrderResult | None:
    """Record a guardrail skip and optionally return it to an event caller.

    Scheduler callers use ``None`` to mean "nothing was sent". The analysis
    WebSocket needs more context, so it opts into a serialisable ``SKIPPED``
    result.
    """
    _record_skip(reason_code)
    if not include_skip_result:
        return None
    return OrderResult(
        order_id="",
        status="SKIPPED",
        filled_price=None,
        filled_quantity=None,
        message=message,
        reason_code=reason_code,
    )


def _safe_float(raw) -> float | None:
    """``float()`` that folds ``None`` and non-numeric values into ``None``."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _as_mapping(raw) -> dict:
    """Decode a mapping or JSON object without allowing malformed AI data through."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _portfolio_decision(row) -> dict:
    """Return the controller-accepted canonical structured decision."""
    return _as_mapping(getattr(row, "portfolio_decision_json", None))


def _trade_date(row) -> date | None:
    """The session an analysis is for, or ``None`` when the row does not say.

    An unknown date is not silently replaced with today's: the exchange gate
    would then be answering a question about a different session than the one
    the analysis was run for.
    """
    raw = getattr(row, "trade_date", None)
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _decision_value(row, *keys: str):
    """Read one value exclusively from the canonical accepted decision."""
    decision = _portfolio_decision(row)
    for key in keys:
        value = decision.get(key)
        if value is not None:
            return value
    return None


def _extract_leverage(row) -> float:
    """Read the accepted structured leverage recommendation, clamped to [1, 10]."""
    value = _safe_float(_decision_value(row, "recommended_leverage"))
    if value is not None and value >= 1.0:
        return min(value, 10.0)
    return 1.0


def _pm_target_notional(row, *, portfolio_equity: float) -> float | None:
    """Return canonical PM *total* target allocation in portfolio currency.

    ``position_size_pct`` is deliberately based on total equity, not free
    cash. This is what makes an Overweight a delta toward a target and an
    Underweight a partial reduction instead of an accidental full exit.
    """
    decision = _portfolio_decision(row)
    allocation_pct = _safe_float(decision.get("position_size_pct"))
    if allocation_pct is None or portfolio_equity <= 0:
        return None
    return max(0.0, min(allocation_pct, 100.0)) / 100.0 * portfolio_equity


def _pm_suggested_order_notional(row) -> float | None:
    """Read the PM's approximate order notional from the canonical decision."""
    value = _safe_float(_portfolio_decision(row).get("suggested_capital"))
    return max(0.0, value) if value is not None else None


def _target_notional_from_suggested_capital(row, *, ticker: str, existing_notional: float) -> float | None:
    """Recover a target allocation from ``suggested_capital`` when it is safe to.

    ``position_size_pct`` is the total allocation *after* the trade, while
    ``suggested_capital`` is the notional of this one order — different
    quantities that coincide only when nothing is held yet. Converting outside
    that case would turn an add into a reset, so this returns ``None`` instead.

    A model that omits the percentage but states the capital has still said what
    it wants; refusing the trade over the unit it chose loses the user a trade
    the analysis recommended.
    """
    if existing_notional > 0:
        return None
    suggested = _pm_suggested_order_notional(row)
    if suggested is None or suggested <= 0:
        return None
    _logger.warning(
        "Auto-order for %s has no position_size_pct; sizing the opening position from "
        "suggested_capital=%.2f instead. Hard risk caps still apply.",
        ticker,
        suggested,
    )
    return suggested


async def _allocation_snapshot(db, *, portfolio) -> dict | None:
    """Read a side-effect-free current-equity snapshot for target allocation."""
    from backend.services.mock_trading_service import get_portfolio_with_live_prices

    try:
        snapshot = await get_portfolio_with_live_prices(
            db,
            portfolio_id=portfolio.id,
            read_only=True,
            release_before_price_io=True,
        )
    except Exception as exc:  # noqa: BLE001 — target allocation must not use stale equity
        _logger.warning("Could not read portfolio equity for final allocation sizing: %s", exc)
        return None
    if not isinstance(snapshot, dict):
        return None
    equity = _safe_float(snapshot.get("total_value"))
    if equity is None or equity <= 0:
        return None
    return snapshot


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
    disabled. Existing positions can always be closed after the setting is
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


async def _apply_portfolio_risk_caps(db, *, portfolio, ticker, price, quantity, settings, snapshot: dict | None = None) -> float:
    """Shrink ``quantity`` so the resulting position respects the portfolio's
    single-name concentration and gross-exposure limits. Returns the (possibly
    reduced) quantity; 0 means the order should be skipped."""
    from backend.services.mock_trading_service import get_portfolio_with_live_prices
    from backend.services.portfolio_risk_service import (
        DEFAULT_MAX_CONCENTRATION_PCT,
        DEFAULT_MAX_GROSS_EXPOSURE,
        cap_order_notional,
    )

    if snapshot is None:
        try:
            snapshot = await get_portfolio_with_live_prices(
                db,
                portfolio_id=portfolio.id,
                read_only=True,
                release_before_price_io=True,
            )
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


async def _get_or_create_broker_audit_portfolio(db: AsyncSession, *, user, mode: str, account: dict):
    """Map authoritative broker balances into the local audit container."""
    equity = safe_decimal(account.get("equity") or account.get("portfolio_value") or 0)
    cash = safe_decimal(account.get("cash") or 0)
    return await _repo_get_or_create_broker_audit_portfolio(
        db,
        user_id=user.id,
        mode=mode,
        equity=equity,
        cash=cash,
    )


def _broker_risk_snapshot(account: dict, positions: dict[str, dict]) -> dict:
    holdings = []
    for position in positions.values():
        market_value = abs(float(position.get("market_value") or 0.0))
        holdings.append(
            {
                "ticker": str(position.get("ticker") or "").upper(),
                "side": str(position.get("side") or "long"),
                "quantity": abs(float(position.get("quantity") or 0.0)),
                "market_value": market_value,
                "current_price": float(position.get("current_price") or 0.0),
            }
        )
    return {
        "total_value": float(account.get("equity") or account.get("portfolio_value") or 0.0),
        "cash_available": float(account.get("cash") or 0.0),
        "buying_power": float(account.get("buying_power") or 0.0),
        "holdings": holdings,
    }


async def _persist_broker_order(
    db: AsyncSession,
    *,
    portfolio,
    request: OrderRequest,
    result: OrderResult,
    side: str,
) -> None:
    """Persist every broker submission/result for reconciliation and audit."""
    filled_qty = safe_decimal(result.filled_quantity or 0)
    filled_price = safe_decimal(result.filled_price) if result.filled_price is not None else None
    total_value = filled_qty * filled_price if filled_price is not None else None
    await _repo_persist_broker_order(
        db,
        portfolio_id=portfolio.id,
        ticker=request.ticker,
        action=request.action,
        side=side,
        leverage=safe_decimal(request.leverage),
        quantity_requested=request.quantity,
        quantity_filled=filled_qty,
        status=result.status,
        price_per_share=filled_price,
        total_value=total_value,
        commission=safe_decimal(result.commission),
        external_order_id=result.order_id or None,
        analysis_id=request.analysis_id,
        ai_signal=request.ai_signal,
        ai_reasoning=request.ai_reasoning,
        executed_at=result.executed_at if filled_qty > 0 else None,
    )


async def place_signal_order(
    db: AsyncSession,
    *,
    ticker: str,
    row,
    settings,
    user=None,
    include_skip_result: bool = False,
) -> OrderResult | None:
    """Size and place an order from one canonical accepted decision.

    Returns the ``OrderResult`` (so callers can persist their own order record),
    or ``None`` when the signal is not actionable or no price is available.
    Set ``include_skip_result`` for an explicit, non-persisted ``SKIPPED``
    outcome with a safe reason code (used by the live analysis stream).
    The caller is responsible for committing the transaction.
    """
    analysis_mode = str(getattr(row, "analysis_mode", "live") or "live").lower()
    if analysis_mode != "live":
        return _skipped_order(
            reason_code="non_live_analysis",
            message="Historical and time-travel analyses are non-executing; no order was sent.",
            include_skip_result=include_skip_result,
        )

    if str(getattr(row, "strategy_update_status", "") or "").lower() == "conflict":
        return _skipped_order(
            reason_code="strategy_conflict",
            message="The asset strategy changed concurrently; this stale analysis cannot place an order.",
            include_skip_result=include_skip_result,
        )

    pm_decision = _portfolio_decision(row)
    if not pm_decision:
        return _skipped_order(
            reason_code="portfolio_decision_missing",
            message="This analysis has no canonical accepted decision; no order was sent.",
            include_skip_result=include_skip_result,
        )

    signal = str(pm_decision.get("rating", "") or "").strip()
    execution_action = str(pm_decision.get("execution_action", "") or "").strip().lower()
    if execution_action in {"no_new_order", "no_order", "freeze"}:
        return _skipped_order(
            reason_code="decision_stability_no_order",
            message="The accepted decision stability contract prohibits a new order.",
            include_skip_result=include_skip_result,
        )
    action = SIGNAL_TO_ACTION.get(signal)
    if action is None:
        if signal == "Hold":
            return _skipped_order(
                reason_code="non_actionable_signal",
                message="The final accepted rating is Hold; no order was sent.",
                include_skip_result=include_skip_result,
            )
        return _skipped_order(
            reason_code="invalid_portfolio_decision",
            message="The canonical accepted rating is not actionable; no order was sent.",
            include_skip_result=include_skip_result,
        )

    persisted_signal = str(getattr(row, "signal", "") or "").strip()
    if persisted_signal and persisted_signal != signal:
        _logger.warning(
            "Analysis signal differs from the canonical accepted rating for %s (%s != %s); using the accepted rating.",
            ticker,
            persisted_signal,
            signal,
        )

    # An order sized against a holiday quote is priced off the previous close
    # and cannot be filled, so no automated buy or sell leaves the building
    # while the instrument's exchange is shut. Crypto has no closed days and is
    # never gated here.
    from backend.services.market_calendar_service import market_closed_reason

    session = _trade_date(row)
    closed_reason = (
        market_closed_reason(session, ticker=ticker, asset_type=getattr(row, "asset_type", None))
        if session is not None
        else None
    )
    if closed_reason:
        _logger.info("Skipping auto-order for %s: %s", ticker, closed_reason)
        return _skipped_order(
            reason_code="market_closed",
            message=closed_reason,
            include_skip_result=include_skip_result,
        )

    if getattr(settings, "quality_gate_enabled", False):
        quality = getattr(row, "quality", None)
        if isinstance(quality, dict) and quality.get("confidence") == "low":
            _logger.info(
                "Quality gate: skipping auto-order for %s (low-confidence run, score=%s)",
                ticker,
                quality.get("score"),
            )
            return _skipped_order(
                reason_code="quality_gate",
                message="The analysis quality gate skipped this order.",
                include_skip_result=include_skip_result,
            )

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
        return _skipped_order(
            reason_code="invalid_trading_configuration",
            message="Server trading configuration is invalid; no order was sent.",
            include_skip_result=include_skip_result,
        )

    if sys_mode == "live":
        if sys_broker != "alpaca":
            _logger.error("Live mode requires the Alpaca broker; skipping order execution")
            return _skipped_order(
                reason_code="invalid_live_broker",
                message="Live trading requires the Alpaca broker; no order was sent.",
                include_skip_result=include_skip_result,
            )
        if not is_live_trading_enabled():
            _logger.warning("Live order skipped because ENABLE_LIVE_TRADING is disabled")
            return _skipped_order(
                reason_code="live_trading_disabled",
                message="Live trading is disabled by server configuration.",
                include_skip_result=include_skip_result,
            )

    if sys_broker == "alpaca":
        if not user or not getattr(user, "is_owner", False):
            _logger.warning("Alpaca broker can only be used by the owner user; skipping order execution")
            return _skipped_order(
                reason_code="broker_not_authorized",
                message="The configured broker is only available to the owner account.",
                include_skip_result=include_skip_result,
            )

    broker_snapshot: dict | None = None
    broker_account: dict | None = None
    broker_positions: dict[str, dict] = {}
    trader = None

    if sys_broker == "alpaca":
        # Alpaca account state is authoritative for cash, equity and positions.
        # The local portfolio is only an immutable/auditable order container.
        trader = get_trader(mode=sys_mode, broker=sys_broker, portfolio_id=0, initial_capital=0, db=db)
        get_snapshot = getattr(trader, "get_account_snapshot", None)
        broker_account = await get_snapshot() if callable(get_snapshot) else {}
        if not broker_account or broker_account.get("trading_blocked") or broker_account.get("account_blocked"):
            return _skipped_order(
                reason_code="broker_account_unavailable",
                message="The broker account is unavailable or blocked; no order was sent.",
                include_skip_result=include_skip_result,
            )
        if float(broker_account.get("equity") or 0.0) <= 0:
            return _skipped_order(
                reason_code="broker_equity_unavailable",
                message="The broker did not report positive account equity; no order was sent.",
                include_skip_result=include_skip_result,
            )
        broker_positions = await trader.get_positions()
        broker_snapshot = _broker_risk_snapshot(broker_account, broker_positions)
        portfolio = await _get_or_create_broker_audit_portfolio(db, user=user, mode=sys_mode, account=broker_account)
        position = broker_positions.get(ticker.upper())
        holding = None
        if position and float(position.get("quantity") or 0.0) > 0:
            holding = SimpleNamespace(
                quantity=safe_decimal(position.get("quantity")),
                side=str(position.get("side") or "long"),
                avg_buy_price=safe_decimal(position.get("avg_price")),
            )
    else:
        portfolio = await get_or_create_sim_portfolio(db, user=user)
        from backend.repositories.portfolio import get_holding

        holding = await get_holding(db, portfolio.id, ticker)
    allow_short = bool(getattr(settings, "allow_short_selling", False))
    if signal == "Underweight":
        if holding is None or getattr(holding, "side", None) != "long":
            return _skipped_order(
                reason_code="no_long_position_to_reduce",
                message="Underweight requires an existing long position to reduce.",
                include_skip_result=include_skip_result,
            )
        intent = "reduce_long"
    else:
        intent = _classify_order_intent(action, getattr(holding, "side", None), allow_short)
    if intent is None:
        _logger.info("Short selling is disabled; skipping new short signal for %s", ticker)
        return _skipped_order(
            reason_code="short_disabled",
            message="Short selling is disabled, so this new short order was not sent.",
            include_skip_result=include_skip_result,
        )
    if sys_broker == "alpaca" and intent == "open_short" and not bool((broker_account or {}).get("shorting_enabled")):
        _logger.info("Alpaca shorting is disabled for the broker account; skipping new short signal for %s", ticker)
        return _skipped_order(
            reason_code="broker_shorting_disabled",
            message="The broker account is not enabled for short selling; no order was sent.",
            include_skip_result=include_skip_result,
        )
    opening_exposure = intent in {"open_long", "open_short"}
    if execution_action == "reduce_only" and opening_exposure:
        return _skipped_order(
            reason_code="decision_stability_reduce_only",
            message="The accepted decision allows only risk reduction, not new exposure.",
            include_skip_result=include_skip_result,
        )
    position_side = "short" if intent in {"open_short", "close_short"} else "long"

    if opening_exposure and getattr(settings, "drawdown_breaker_enabled", False):
        try:
            initial_capital = _safe_float(portfolio.initial_capital)
            max_drawdown_pct = _safe_float(getattr(settings, "max_portfolio_drawdown_pct", 20.0))
            if initial_capital is None or initial_capital <= 0 or max_drawdown_pct is None or max_drawdown_pct < 0:
                raise ValueError("invalid portfolio capital or drawdown threshold")

            if broker_snapshot is not None:
                snapshot = broker_snapshot
            else:
                from backend.services.mock_trading_service import get_portfolio_with_live_prices

                snapshot = await get_portfolio_with_live_prices(
                    db,
                    portfolio_id=portfolio.id,
                    read_only=True,
                    release_before_price_io=True,
                )
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
                return _skipped_order(
                    reason_code="drawdown_breaker",
                    message="The drawdown circuit breaker skipped this new order.",
                    include_skip_result=include_skip_result,
                )
        except Exception as exc:  # noqa: BLE001 — unsafe breaker state must not open exposure
            _logger.warning("Drawdown breaker check failed for %s; skipping new order: %s", ticker, exc)
            return _skipped_order(
                reason_code="drawdown_snapshot_unavailable",
                message="Portfolio risk data was unavailable, so no new order was sent.",
                include_skip_result=include_skip_result,
            )

    if trader is None:
        trader = get_trader(
            mode=sys_mode,
            broker=sys_broker,
            portfolio_id=portfolio.id,
            initial_capital=float(safe_decimal(portfolio.initial_capital)),
            db=db,
        )
    price = _safe_float(await trader.get_current_price(ticker))
    if price is None or price <= 0:
        _logger.warning("No price available for %s; skipping order execution", ticker)
        return _skipped_order(
            reason_code="price_unavailable",
            message="No valid market price was available, so no order was sent.",
            include_skip_result=include_skip_result,
        )

    raw_stop_loss = _decision_value(row, "stop_loss")
    raw_take_profit = _decision_value(row, "take_profit_price")

    if opening_exposure:
        stop_loss, take_profit = _directional_exit_levels(position_side, price, raw_stop_loss, raw_take_profit)
        strict_stop_loss_mode = bool(getattr(settings, "strict_stop_loss_mode", False))
        if strict_stop_loss_mode and stop_loss is None:
            _logger.warning(
                "Strict stop-loss mode enabled and no valid %s stop-loss found for %s; skipping order execution",
                position_side,
                ticker,
            )
            return _skipped_order(
                reason_code="invalid_stop_loss",
                message="Strict stop-loss mode requires a valid stop level; no order was sent.",
                include_skip_result=include_skip_result,
            )
        if not strict_stop_loss_mode:
            default_stop, default_target = _default_exit_levels(position_side, price)
            stop_loss = stop_loss if stop_loss is not None else default_stop
            take_profit = take_profit if take_profit is not None else default_target

        available_cash = safe_decimal(
            (broker_account or {}).get("cash") if broker_account is not None else portfolio.cash_available
        )
        if available_cash <= 0:
            _logger.info("No available cash for a new %s position in %s; skipping order", position_side, ticker)
            return _skipped_order(
                reason_code="cash_unavailable",
                message="There is no available cash for a new position.",
                include_skip_result=include_skip_result,
            )
        capital = float(available_cash)
        base_risk_pct = _safe_float(getattr(settings, "max_risk_per_trade_pct", None))
        max_position_size_pct = _safe_float(getattr(settings, "max_position_size_pct", None))
        if base_risk_pct is None or base_risk_pct <= 0 or max_position_size_pct is None or max_position_size_pct <= 0:
            _logger.warning("Invalid risk sizing configuration; skipping auto-order for %s", ticker)
            return _skipped_order(
                reason_code="invalid_risk_settings",
                message="Risk-sizing settings are invalid, so no order was sent.",
                include_skip_result=include_skip_result,
            )

        allocation_snapshot = broker_snapshot or await _allocation_snapshot(db, portfolio=portfolio)
        if allocation_snapshot is None:
            return _skipped_order(
                reason_code="portfolio_equity_unavailable",
                message="Current portfolio equity was unavailable, so the target allocation was not traded.",
                include_skip_result=include_skip_result,
            )
        total_equity = _safe_float(allocation_snapshot.get("total_value"))
        if total_equity is None or total_equity <= 0:
            return _skipped_order(
                reason_code="portfolio_equity_unavailable",
                message="Current portfolio equity was unavailable, so the target allocation was not traded.",
                include_skip_result=include_skip_result,
            )
        existing_notional = (
            price * float(safe_decimal(holding.quantity))
            if holding is not None and getattr(holding, "side", None) == "long"
            else 0.0
        )
        target_notional = _pm_target_notional(row, portfolio_equity=total_equity)
        if target_notional is None:
            target_notional = _target_notional_from_suggested_capital(
                row, ticker=ticker, existing_notional=existing_notional
            )
        if target_notional is None:
            _logger.warning(
                "Auto-order for %s skipped: the accepted decision carries no position_size_pct "
                "(rating=%s, suggested_capital=%s). The model omitted the sole sizing input.",
                ticker,
                pm_decision.get("rating"),
                pm_decision.get("suggested_capital"),
            )
            return _skipped_order(
                reason_code="target_allocation_missing",
                message=(
                    "The analysis recommended a trade but gave no target allocation, "
                    "so there was nothing to size the order from."
                ),
                include_skip_result=include_skip_result,
            )
        target_addition = max(0.0, target_notional - existing_notional)
        if target_addition <= 0:
            return _skipped_order(
                reason_code="target_allocation_met",
                message="The current position already meets or exceeds the final target allocation.",
                include_skip_result=include_skip_result,
            )
        pm_target_quantity = target_addition / price
        requested_allocation_pct = _safe_float(pm_decision.get("position_size_pct"))
        if requested_allocation_pct is not None:
            max_position_size_pct = min(max_position_size_pct, max(0.0, requested_allocation_pct))

        quantity = _position_quantity(
            base_risk_pct,
            capital,
            price,
            stop_loss=stop_loss,
            max_position_size_pct=max_position_size_pct,
        )
        pm_suggested_capital = _pm_suggested_order_notional(row)
        quantity = min(quantity, pm_target_quantity)
        if pm_suggested_capital is not None:
            quantity = min(quantity, pm_suggested_capital / price)
        if quantity <= 0:
            _logger.info("Risk sizing left no room for %s; skipping order", ticker)
            return _skipped_order(
                reason_code="position_size_zero",
                message="Risk sizing produced a zero quantity; no order was sent.",
                include_skip_result=include_skip_result,
            )
        quantity = await _apply_portfolio_risk_caps(
            db,
            portfolio=portfolio,
            ticker=ticker,
            price=price,
            quantity=quantity,
            settings=settings,
            snapshot=allocation_snapshot,
        )
        if quantity <= 0:
            _logger.info("Portfolio risk caps left no room for %s; skipping order", ticker)
            return _skipped_order(
                reason_code="portfolio_risk_cap",
                message="Portfolio risk caps left no room for this new order.",
                include_skip_result=include_skip_result,
            )
        leverage = _extract_leverage(row)
    else:
        if holding is None:
            _logger.warning("No existing %s position found to close for %s", position_side, ticker)
            return _skipped_order(
                reason_code="position_not_found",
                message="There is no matching open position to close.",
                include_skip_result=include_skip_result,
            )
        quantity = float(safe_decimal(holding.quantity))
        if quantity <= 0:
            _logger.warning("Existing %s position for %s has no quantity to close", position_side, ticker)
            return _skipped_order(
                reason_code="position_size_zero",
                message="The matching open position has no quantity to close.",
                include_skip_result=include_skip_result,
            )
        if intent == "reduce_long":
            allocation_snapshot = broker_snapshot or await _allocation_snapshot(db, portfolio=portfolio)
            if allocation_snapshot is None:
                return _skipped_order(
                    reason_code="portfolio_equity_unavailable",
                    message="Current portfolio equity was unavailable, so the target allocation was not traded.",
                    include_skip_result=include_skip_result,
                )
            total_equity = _safe_float(allocation_snapshot.get("total_value"))
            if total_equity is None or total_equity <= 0:
                return _skipped_order(
                    reason_code="portfolio_equity_unavailable",
                    message="Current portfolio equity was unavailable, so the target allocation was not traded.",
                    include_skip_result=include_skip_result,
                )
            # suggested_capital cannot stand in here: it is this order's
            # notional, while a reduction needs the target to remain *held*.
            target_notional = _pm_target_notional(row, portfolio_equity=total_equity)
            if target_notional is None:
                _logger.warning(
                    "Auto-order for %s skipped: Underweight carries no position_size_pct.", ticker
                )
                return _skipped_order(
                    reason_code="target_allocation_missing",
                    message=(
                        "The analysis recommended reducing the position but gave no target "
                        "allocation, so there was nothing to size the reduction against."
                    ),
                    include_skip_result=include_skip_result,
                )
            current_notional = price * quantity
            reduction_notional = max(0.0, current_notional - target_notional)
            if reduction_notional <= 0:
                return _skipped_order(
                    reason_code="target_allocation_met",
                    message="The current position is already at or below the final target allocation.",
                    include_skip_result=include_skip_result,
                )
            pm_suggested_capital = _pm_suggested_order_notional(row)
            if pm_suggested_capital is not None and not math.isclose(
                pm_suggested_capital,
                reduction_notional,
                rel_tol=0.15,
                abs_tol=max(1.0, price * 0.01),
            ):
                _logger.warning(
                    "Decision sizing is inconsistent for %s: target reduction %.2f vs suggested %.2f; "
                    "using the target allocation delta",
                    ticker,
                    reduction_notional,
                    pm_suggested_capital,
                )
            quantity = min(quantity, reduction_notional / price)
        stop_loss = None
        take_profit = None
        leverage = 1.0

    request = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=safe_decimal(quantity),
        reference_price=safe_decimal(price),
        analysis_id=getattr(row, "id", None),
        ai_signal=signal,
        ai_reasoning=(getattr(row, "final_decision", "") or "")[:4_000],
        leverage=leverage,
        stop_loss=safe_decimal(stop_loss) if opening_exposure and stop_loss else None,
        take_profit=safe_decimal(take_profit) if opening_exposure and take_profit else None,
        allow_short=allow_short,
    )
    result = await trader.place_order(request)
    if sys_broker == "alpaca":
        try:
            await _persist_broker_order(db, portfolio=portfolio, request=request, result=result, side=position_side)
        except Exception:
            # The broker request already escaped PostgreSQL and cannot be undone.
            # Never collapse an audit-write failure into a generic execution
            # error/rejection: the operator must reconcile the broker account
            # before another order can safely be attempted.
            await db.rollback()
            _logger.exception(
                "Broker order returned but local audit persistence failed ticker=%s external_order_id=%s",
                ticker,
                result.order_id,
            )
            result.status = "RECONCILIATION_REQUIRED"
            result.reason_code = "broker_audit_persist_failed"
            result.message = (
                "The broker order may be live, but its local audit record could not be persisted. "
                "Reconcile the Alpaca account before retrying."
            )
            result.external_submission = True
            return result

        # Refresh the local audit balances from the broker after submission when possible.
        # AlpacaTrader releases/commits the audit transaction before this network
        # request, making the order record durable even if refresh later fails.
        get_snapshot = getattr(trader, "get_account_snapshot", None)
        if callable(get_snapshot):
            refreshed = await get_snapshot()
            if refreshed:
                _repo_apply_broker_account_balances(
                    portfolio,
                    cash=safe_decimal(refreshed.get("cash") or portfolio.cash_available),
                    equity=safe_decimal(refreshed.get("equity") or portfolio.current_balance),
                )
    _logger.info("Order placed: %s %s %s -> %s", action, quantity, ticker, result.status)
    if result.filled_quantity and result.filled_price:
        try:
            from backend.services.notification_service import notify_trade_executed

            await notify_trade_executed(ticker, action, result.filled_quantity, result.filled_price, settings)
        except Exception as exc:
            _logger.warning("trade_executed webhook failed (non-fatal): %s", exc)

    return result
