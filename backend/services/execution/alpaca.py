"""Alpaca execution through the official ``alpaca-py`` SDK only."""

from __future__ import annotations

import asyncio
import logging

from backend.core.config import is_live_trading_enabled
from backend.core.database import AsyncSessionLocal
from backend.core.money import safe_decimal
from backend.services.market_data_service import get_live_price as _get_price

from .base import BaseTraderInterface, OrderRequest, OrderResult

_logger = logging.getLogger(__name__)
_TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def _value(value) -> str:
    return str(getattr(value, "value", value) or "")


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
            price = float(getattr(trade, "price", 0.0) or 0.0)
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
            )
        if request.quantity <= 0:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Order quantity must be positive",
            )

        submission_started = False
        try:
            from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

            trading, _market = await self._clients()
            kwargs = {
                "symbol": request.ticker.upper(),
                "qty": float(request.quantity),
                "side": OrderSide.BUY if request.action.upper() == "BUY" else OrderSide.SELL,
                "time_in_force": TimeInForce.DAY,
            }
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
            status = _value(getattr(order, "status", "UNKNOWN")).upper()
            filled_price = getattr(order, "filled_avg_price", None)
            filled_qty = getattr(order, "filled_qty", None)

            for _ in range(20):
                if status in _TERMINAL:
                    break
                await asyncio.sleep(0.5)
                order = await asyncio.to_thread(trading.get_order_by_id, order_id)
                status = _value(getattr(order, "status", status)).upper()
                filled_price = getattr(order, "filled_avg_price", filled_price)
                filled_qty = getattr(order, "filled_qty", filled_qty)

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

            reason_code = ""
            if status == "FILLED" and (not filled_price or not filled_qty):
                status = "RECONCILIATION_REQUIRED"
                reason_code = "broker_fill_details_missing"

            return OrderResult(
                order_id=order_id,
                status=status,
                filled_price=safe_decimal(filled_price),
                filled_quantity=safe_decimal(filled_qty),
                message=f"Alpaca order status: {status}",
                reason_code=reason_code,
                external_submission=True,
            )
        except Exception:
            _logger.exception("alpaca-py order placement failed")
            status = "RECONCILIATION_REQUIRED" if submission_started else "REJECTED"
            return OrderResult(
                order_id="",
                status=status,
                filled_price=None,
                filled_quantity=None,
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
            return {
                "cash": float(getattr(account, "cash", 0.0) or 0.0),
                "buying_power": float(getattr(account, "buying_power", 0.0) or 0.0),
                "equity": float(getattr(account, "equity", 0.0) or 0.0),
                "portfolio_value": float(getattr(account, "portfolio_value", 0.0) or 0.0),
                "status": _value(getattr(account, "status", "")),
                "trading_blocked": bool(getattr(account, "trading_blocked", False)),
                "account_blocked": bool(getattr(account, "account_blocked", False)),
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
                symbol = str(getattr(pos, "symbol", "")).upper()
                qty = float(getattr(pos, "qty", 0.0) or 0.0)
                side = _value(getattr(pos, "side", "short" if qty < 0 else "long")).lower()
                result[symbol] = {
                    "ticker": symbol,
                    "quantity": abs(qty),
                    "signed_quantity": qty,
                    "side": side,
                    "avg_price": float(getattr(pos, "avg_entry_price", 0.0) or 0.0),
                    "current_price": float(getattr(pos, "current_price", 0.0) or 0.0),
                    "market_value": abs(float(getattr(pos, "market_value", 0.0) or 0.0)),
                    "unrealized_pnl": float(getattr(pos, "unrealized_pl", 0.0) or 0.0),
                }
            return result
        except Exception as exc:
            _logger.warning("alpaca-py positions request failed: %s", exc)
            return {}

    async def close(self) -> None:
        if self._is_local_db and self._db is not None:
            await self._db.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
