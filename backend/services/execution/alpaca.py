"""Alpaca execution through the official ``alpaca-py`` SDK only."""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from decimal import Decimal, InvalidOperation

from backend.core.config import is_live_trading_enabled
from backend.core.database import AsyncSessionLocal
from backend.core.money import safe_decimal
from backend.services.market_data_service import get_live_price as _get_price

from .base import BaseTraderInterface, OrderRequest, OrderResult

_logger = logging.getLogger(__name__)
_TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def _value(value) -> str:
    return str(getattr(value, "value", value) or "")


def _finite_float(value, *, field: str) -> float:
    parsed = float(value or 0.0)
    if not math.isfinite(parsed):
        raise ValueError(f"Alpaca returned non-finite {field}")
    return parsed


def _broker_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Alpaca returned an invalid decimal value") from exc
    if not parsed.is_finite():
        raise ValueError("Alpaca returned a non-finite decimal value")
    return parsed


def _validated_fill_details(raw_price, raw_quantity, *, requested_quantity):
    """Return safe broker fill values plus an inconsistency reason, if any."""
    try:
        price = _broker_decimal(raw_price)
        quantity = _broker_decimal(raw_quantity)
        requested = _broker_decimal(requested_quantity)
    except ValueError:
        return None, None, "broker_fill_details_invalid"

    if price < 0 or quantity < 0 or requested <= 0:
        return None, None, "broker_fill_details_invalid"
    if quantity > requested:
        return None, None, "broker_fill_details_invalid"
    if (quantity > 0) != (price > 0):
        return None, None, "broker_fill_details_invalid"
    return (price if price > 0 else None), (quantity if quantity > 0 else None), ""


def _analysis_client_order_id(request: OrderRequest, action: str) -> str | None:
    """Stable Alpaca correlation id for the one auto-order owned by an analysis.

    A lost HTTP response must not turn a retry into a second broker order.  The
    analysis row is the durable execution identity, so derive a compact UUID5
    from it. Direct/manual adapter calls without an analysis id retain Alpaca's
    normal server-generated client id behavior.
    """
    if request.analysis_id is None:
        return None
    seed = f"tradingagents:{request.analysis_id}:{request.ticker.strip().upper()}:{action}"
    return f"ta-{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


class AlpacaTrader(BaseTraderInterface):
    """Paper/live broker adapter backed exclusively by ``alpaca-py``."""

    def __init__(
        self,
        portfolio_id: int = 1,
        initial_capital: float = 100_000.0,
        db=None,
        mode: str = "simulation",
        release_db_before_network: bool = False,
    ):
        if db is None:
            db = AsyncSessionLocal()
            self._is_local_db = True
        else:
            self._is_local_db = False
        self._db = db
        self._portfolio_id = portfolio_id
        self._initial_capital = initial_capital
        self._mode = mode
        self._release_db_before_network = release_db_before_network

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def broker_name(self) -> str:
        return "alpaca"

    async def _get_credentials(self) -> tuple[str, str]:
        from sqlalchemy import select

        from backend.core.config import get_settings
        from backend.models.user import User
        from backend.services.user_service import get_user_api_key

        result = await self._db.execute(select(User).where(User.role == "owner"))
        owner = result.scalar_one_or_none()
        if not owner:
            raise ValueError("No owner user found to load Alpaca credentials")

        fernet = get_settings().get_fernet()
        key = get_user_api_key(owner, "alpaca_key", fernet)
        secret = get_user_api_key(owner, "alpaca_secret", fernet)
        if not key or not secret:
            raise ValueError("Alpaca API credentials missing or invalid. Set them in Owner Profile.")

        if self._release_db_before_network:
            # Every public broker method calls _clients() immediately before
            # entering alpaca-py network I/O. End whatever short DB phase was
            # needed to load credentials/config/audit state so a slow broker
            # request never pins a SQL connection or row lock. Alpaca side
            # effects cannot be transactionally rolled back with PostgreSQL;
            # making the DB boundary explicit is safer than pretending they can.
            await self._db.commit()
        return key, secret

    async def _clients(self):
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise RuntimeError(
                "alpaca-py is required for Alpaca execution. Sync backend dependencies before using Alpaca."
            ) from exc

        key, secret = await self._get_credentials()
        trading = TradingClient(key, secret, paper=self._mode != "live")
        market = StockHistoricalDataClient(key, secret)
        return trading, market

    async def get_current_price(self, ticker: str) -> float | None:
        try:
            from alpaca.data.requests import StockLatestTradeRequest

            _trading, market = await self._clients()
            request = StockLatestTradeRequest(symbol_or_symbols=ticker.upper())
            result = await asyncio.to_thread(market.get_stock_latest_trade, request)
            trade = result.get(ticker.upper()) if isinstance(result, dict) else None
            price = _finite_float(getattr(trade, "price", 0.0), field=f"{ticker} latest-trade price")
            if price > 0:
                return price
        except Exception as exc:
            _logger.warning("alpaca-py latest trade failed for %s: %s", ticker, exc)

        # Real-money sizing fails closed. Paper mode can still use the normal
        # market-data service when Alpaca's data endpoint is transiently down.
        if self._mode == "live":
            return None
        return await _get_price(ticker)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        if self._mode == "live" and not is_live_trading_enabled():
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Live Alpaca trading is disabled by server configuration.",
                reason_code="live_trading_disabled",
            )

        action = str(request.action or "").strip().upper()
        if action not in {"BUY", "SELL"}:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Order action must be BUY or SELL.",
                reason_code="invalid_action",
            )

        quantity = safe_decimal(request.quantity)
        if not quantity.is_finite() or quantity <= 0:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Order quantity must be a positive finite number.",
                reason_code="invalid_quantity",
            )

        client_order_id = _analysis_client_order_id(request, action)
        submission_started = False
        known_order_id = ""
        known_filled_price = None
        known_filled_qty = None
        trading = None
        try:
            from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

            trading, _market = await self._clients()
            kwargs = {
                "symbol": request.ticker.upper(),
                "qty": float(quantity),
                "side": OrderSide.BUY if action == "BUY" else OrderSide.SELL,
                "time_in_force": TimeInForce.DAY,
            }
            if client_order_id:
                kwargs["client_order_id"] = client_order_id
            if request.stop_loss and request.take_profit:
                kwargs["order_class"] = OrderClass.BRACKET
                kwargs["take_profit"] = TakeProfitRequest(limit_price=float(request.take_profit))
                kwargs["stop_loss"] = StopLossRequest(stop_price=float(request.stop_loss))
            elif request.stop_loss or request.take_profit:
                kwargs["order_class"] = OrderClass.OTO
                if request.stop_loss:
                    kwargs["stop_loss"] = StopLossRequest(stop_price=float(request.stop_loss))
                if request.take_profit:
                    kwargs["take_profit"] = TakeProfitRequest(limit_price=float(request.take_profit))

            # Construct and validate the SDK request entirely locally first. A
            # validation error here proves nothing was submitted and is safe to
            # report as a rejection. Only flip the uncertainty flag immediately
            # before entering submit_order, where a timeout may hide acceptance.
            broker_request = MarketOrderRequest(**kwargs)
            submission_started = True
            order = await asyncio.to_thread(trading.submit_order, broker_request)
            order_id = str(getattr(order, "id", "") or "")
            known_order_id = order_id
            status = _value(getattr(order, "status", "UNKNOWN")).upper()
            filled_price = getattr(order, "filled_avg_price", None)
            filled_qty = getattr(order, "filled_qty", None)
            known_filled_price = filled_price
            known_filled_qty = filled_qty

            for _ in range(20):
                if status in _TERMINAL:
                    break
                await asyncio.sleep(0.5)
                order = await asyncio.to_thread(trading.get_order_by_id, order_id)
                status = _value(getattr(order, "status", status)).upper()
                filled_price = getattr(order, "filled_avg_price", filled_price)
                filled_qty = getattr(order, "filled_qty", filled_qty)
                known_filled_price = filled_price
                known_filled_qty = filled_qty

            if status not in _TERMINAL:
                try:
                    await asyncio.to_thread(trading.cancel_order_by_id, order_id)
                except Exception as exc:
                    _logger.warning("Could not cancel uncompleted Alpaca order %s: %s", order_id, exc)
                await asyncio.sleep(0.25)
                order = await asyncio.to_thread(trading.get_order_by_id, order_id)
                status = _value(getattr(order, "status", status)).upper()
                filled_price = getattr(order, "filled_avg_price", filled_price)
                filled_qty = getattr(order, "filled_qty", filled_qty)
                known_filled_price = filled_price
                known_filled_qty = filled_qty

            safe_filled_price, safe_filled_qty, fill_reason = _validated_fill_details(
                filled_price,
                filled_qty,
                requested_quantity=quantity,
            )
            reason_code = fill_reason
            if fill_reason:
                status = "RECONCILIATION_REQUIRED"
            elif status not in _TERMINAL:
                status = "RECONCILIATION_REQUIRED"
                reason_code = "broker_order_still_open"
            elif status == "FILLED" and (safe_filled_price is None or safe_filled_qty is None):
                status = "RECONCILIATION_REQUIRED"
                reason_code = "broker_fill_details_missing"

            return OrderResult(
                order_id=order_id,
                status=status,
                filled_price=safe_filled_price,
                filled_quantity=safe_filled_qty,
                message=(
                    "Broker order state is not safely terminal; reconcile the Alpaca account before retrying."
                    if status == "RECONCILIATION_REQUIRED"
                    else f"Alpaca order status: {status}"
                ),
                reason_code=reason_code,
                external_submission=True,
            )
        except Exception:
            _logger.exception("alpaca-py order placement failed")

            # If submit_order lost its response, the deterministic client id is
            # the safest way to ask Alpaca whether the order actually exists.
            # A confirmed lookup can turn an ambiguous timeout into a concrete
            # terminal result without ever submitting a second order.
            if submission_started and not known_order_id and client_order_id and trading is not None:
                try:
                    recovered = await asyncio.to_thread(trading.get_order_by_client_id, client_order_id)
                    recovered_id = str(getattr(recovered, "id", "") or "")
                    recovered_status = _value(getattr(recovered, "status", "UNKNOWN")).upper()
                    recovered_price = getattr(recovered, "filled_avg_price", None)
                    recovered_qty = getattr(recovered, "filled_qty", None)
                    safe_price, safe_qty, fill_reason = _validated_fill_details(
                        recovered_price,
                        recovered_qty,
                        requested_quantity=quantity,
                    )
                    reason_code = fill_reason
                    if fill_reason:
                        recovered_status = "RECONCILIATION_REQUIRED"
                    elif recovered_status not in _TERMINAL:
                        recovered_status = "RECONCILIATION_REQUIRED"
                        reason_code = "broker_order_still_open"
                    elif recovered_status == "FILLED" and (safe_price is None or safe_qty is None):
                        recovered_status = "RECONCILIATION_REQUIRED"
                        reason_code = "broker_fill_details_missing"

                    return OrderResult(
                        order_id=recovered_id or f"client:{client_order_id}",
                        status=recovered_status,
                        filled_price=safe_price,
                        filled_quantity=safe_qty,
                        message=(
                            "Broker submission was recovered by client order id; reconcile before retrying."
                            if recovered_status == "RECONCILIATION_REQUIRED"
                            else f"Alpaca order status: {recovered_status}"
                        ),
                        reason_code=reason_code,
                        external_submission=True,
                    )
                except Exception as recovery_exc:
                    _logger.warning(
                        "Could not recover uncertain Alpaca submission by client_order_id=%s: %s",
                        client_order_id,
                        recovery_exc,
                    )
                    # Preserve a durable, explicitly typed reference in the
                    # existing external-order audit field. No production code
                    # treats this value as a broker UUID, and the prefix makes
                    # the distinction unambiguous to operators.
                    known_order_id = f"client:{client_order_id}"

            status = "RECONCILIATION_REQUIRED" if submission_started else "REJECTED"
            safe_filled_price, safe_filled_qty, _fill_reason = _validated_fill_details(
                known_filled_price,
                known_filled_qty,
                requested_quantity=quantity,
            )
            return OrderResult(
                order_id=known_order_id,
                status=status,
                filled_price=safe_filled_price if submission_started else None,
                filled_quantity=safe_filled_qty if submission_started else None,
                message=(
                    "Broker submission outcome is uncertain; reconcile the Alpaca account before retrying."
                    if submission_started
                    else "Broker order request failed before submission. Review server logs."
                ),
                reason_code="broker_submission_uncertain" if submission_started else "broker_request_failed",
                external_submission=submission_started,
            )

    async def cancel_order(self, order_id: str) -> bool:
        if self._mode == "live" and not is_live_trading_enabled():
            return False
        try:
            trading, _market = await self._clients()
            await asyncio.to_thread(trading.cancel_order_by_id, order_id)
            return True
        except Exception as exc:
            _logger.warning("alpaca-py cancellation failed for %s: %s", order_id, exc)
            return False

    async def get_account_snapshot(self) -> dict[str, float | str | bool]:
        try:
            trading, _market = await self._clients()
            account = await asyncio.to_thread(trading.get_account)
            account_status = _value(getattr(account, "status", "")).upper()
            trade_suspended = bool(getattr(account, "trade_suspended_by_user", False))
            status_allows_trading = account_status in {"ACTIVE", "PAPER_ONLY"}
            return {
                "cash": _finite_float(getattr(account, "cash", 0.0), field="account cash"),
                "buying_power": _finite_float(getattr(account, "buying_power", 0.0), field="account buying power"),
                "equity": _finite_float(getattr(account, "equity", 0.0), field="account equity"),
                "portfolio_value": _finite_float(
                    getattr(account, "portfolio_value", 0.0), field="account portfolio value"
                ),
                "status": account_status,
                "trading_blocked": (
                    bool(getattr(account, "trading_blocked", False))
                    or trade_suspended
                    or not status_allows_trading
                ),
                "account_blocked": bool(getattr(account, "account_blocked", False)),
                "trade_suspended_by_user": trade_suspended,
                "shorting_enabled": bool(getattr(account, "shorting_enabled", False)),
            }
        except Exception as exc:
            _logger.warning("alpaca-py account request failed: %s", exc)
            return {}

    async def get_balance(self) -> float:
        return float((await self.get_account_snapshot()).get("cash") or 0.0)

    async def get_positions(self) -> dict[str, dict]:
        try:
            trading, _market = await self._clients()
            positions = await asyncio.to_thread(trading.get_all_positions)
            result: dict[str, dict] = {}
            for pos in positions:
                symbol = str(getattr(pos, "symbol", "") or "").strip().upper()
                if not symbol:
                    raise ValueError("Alpaca returned a position without a symbol")

                qty = _finite_float(getattr(pos, "qty", 0.0), field=f"{symbol} quantity")
                side = _value(getattr(pos, "side", "")).lower()
                if side not in {"long", "short"}:
                    raise ValueError(f"Alpaca returned invalid {symbol} position side {side!r}")

                quantity = abs(qty)
                if quantity == 0:
                    continue
                avg_price = _finite_float(getattr(pos, "avg_entry_price", 0.0), field=f"{symbol} average price")
                current_price = _finite_float(getattr(pos, "current_price", 0.0), field=f"{symbol} current price")
                market_value = abs(
                    _finite_float(getattr(pos, "market_value", 0.0), field=f"{symbol} market value")
                )
                unrealized_pnl = _finite_float(
                    getattr(pos, "unrealized_pl", 0.0), field=f"{symbol} unrealized PnL"
                )
                if avg_price <= 0 or current_price <= 0 or market_value <= 0:
                    raise ValueError(f"Alpaca returned incomplete valuation data for {symbol}")

                result[symbol] = {
                    "ticker": symbol,
                    "quantity": quantity,
                    "signed_quantity": -quantity if side == "short" else quantity,
                    "side": side,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                }
            return result
        except Exception as exc:
            _logger.warning("alpaca-py positions request failed: %s", exc)
            raise RuntimeError("Alpaca positions are unavailable; refusing to assume an empty account.") from exc

    async def close(self) -> None:
        if self._is_local_db and self._db is not None:
            await self._db.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
