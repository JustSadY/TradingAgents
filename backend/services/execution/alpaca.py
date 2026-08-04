import asyncio
import logging

import httpx

import backend.bootstrap  # noqa: F401
from backend.core.config import is_live_trading_enabled
from backend.core.database import AsyncSessionLocal
from backend.core.money import safe_decimal
from backend.services.market_data_service import get_live_price as _get_price

from .base import BaseTraderInterface, OrderRequest, OrderResult

_logger = logging.getLogger(__name__)

class AlpacaTrader(BaseTraderInterface):
    def __init__(self, portfolio_id: int = 1, initial_capital: float = 100_000.0, db=None, mode: str = "simulation"):
        if db is None:
            db = AsyncSessionLocal()
            self._is_local_db = True
        else:
            self._is_local_db = False
        self._db = db
        self._portfolio_id = portfolio_id
        self._initial_capital = initial_capital
        self._mode = mode

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def broker_name(self) -> str:
        return "alpaca"

    @property
    def base_url(self) -> str:
        if self._mode == "live":
            return "https://api.alpaca.markets"
        return "https://paper-api.alpaca.markets"

    async def _get_credentials(self) -> tuple[str | None, str | None]:
        from sqlalchemy import select

        from backend.core.config import get_settings
        from backend.models.user import User
        from backend.services.user_service import get_user_api_key

        try:
            result = await self._db.execute(select(User).where(User.role == "owner"))
            owner = result.scalar_one_or_none()
            if not owner:
                _logger.warning("No owner user found in database to load Alpaca credentials.")
                return None, None

            fernet = get_settings().get_fernet()
            alpaca_key = get_user_api_key(owner, "alpaca_key", fernet)
            alpaca_secret = get_user_api_key(owner, "alpaca_secret", fernet)
            return alpaca_key, alpaca_secret
        except Exception as e:
            _logger.exception("Failed to query owner Alpaca credentials: %s", e)
            return None, None

    async def _get_headers(self) -> dict[str, str]:
        key, secret = await self._get_credentials()
        if not key or not secret:
            raise ValueError("Alpaca API credentials missing or invalid. Set them in Owner Profile.")
        return {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        }

    async def get_current_price(self, ticker: str) -> float | None:
        """Get a broker-side latest trade for sizing live/paper orders.

        A broker order must not be sized from an unrelated delayed provider.
        Paper mode may use Yahoo only when the Alpaca market-data endpoint is
        temporarily unavailable; live mode fails closed.
        """
        try:
            headers = await self._get_headers()
            url = f"https://data.alpaca.markets/v2/stocks/{ticker.upper()}/trades/latest"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, params={"feed": "iex"}, timeout=5.0)
                if resp.status_code == 200:
                    trade = (resp.json() or {}).get("trade") or {}
                    price = float(trade.get("p") or 0.0)
                    if price > 0:
                        return price
                _logger.warning("Alpaca latest-trade request failed for %s (HTTP %s)", ticker, resp.status_code)
        except Exception as exc:
            _logger.warning("Alpaca latest-trade request failed for %s: %s", ticker, exc)
        if self._mode == "live":
            return None
        return await _get_price(ticker)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        if self._mode == "live" and not is_live_trading_enabled():
            _logger.warning("Blocked live Alpaca order because ENABLE_LIVE_TRADING is disabled")
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Live Alpaca trading is disabled by server configuration.",
            )
        try:
            headers = await self._get_headers()
        except ValueError as exc:
            _logger.exception("Alpaca place_order failed")
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message=str(exc),
            )
        qty_str = f"{request.quantity:.4f}".rstrip("0").rstrip(".")
        if not qty_str or float(qty_str) <= 0:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Order quantity must be positive",
            )

        body = {
            "symbol": request.ticker.upper(),
            "qty": qty_str,
            "side": request.action.lower(),
            "type": "market",
            "time_in_force": "day",
        }
        if request.stop_loss or request.take_profit:
            if request.stop_loss and request.take_profit:
                body["order_class"] = "bracket"
                body["take_profit"] = {"limit_price": f"{request.take_profit:.2f}"}
                body["stop_loss"] = {"stop_price": f"{request.stop_loss:.2f}"}
            elif request.stop_loss:
                body["order_class"] = "oto"
                body["stop_loss"] = {"stop_price": f"{request.stop_loss:.2f}"}
            elif request.take_profit:
                body["order_class"] = "oto"
                body["take_profit"] = {"limit_price": f"{request.take_profit:.2f}"}

        url = f"{self.base_url}/v2/orders"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=body, headers=headers, timeout=10.0)
                if resp.status_code != 200:
                    _logger.error("Alpaca API error %s: %s", resp.status_code, resp.text)
                    err_msg = f"Alpaca rejected the order (HTTP {resp.status_code})"
                    return OrderResult(
                        order_id="",
                        status="REJECTED",
                        filled_price=None,
                        filled_quantity=None,
                        message=err_msg,
                    )

                data = resp.json()
                order_id = data.get("id", "")
                status = (data.get("status") or "UNKNOWN").upper()
                filled_price = None
                filled_qty = None
                if data.get("filled_avg_price"):
                    filled_price = float(data["filled_avg_price"])
                if data.get("filled_qty"):
                    filled_qty = float(data["filled_qty"])
                terminal = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
                # PARTIALLY_FILLED is not terminal. Keep following the broker
                # order; if our bounded wait expires, cancel the remainder and
                # persist only the actual broker-reported fill.
                for _ in range(20):
                    if status in terminal:
                        break
                    await asyncio.sleep(0.5)
                    chk_resp = await client.get(f"{url}/{order_id}", headers=headers, timeout=5.0)
                    if chk_resp.status_code == 200:
                        chk_data = chk_resp.json()
                        status = (chk_data.get("status") or "UNKNOWN").upper()
                        if chk_data.get("filled_avg_price"):
                            filled_price = float(chk_data["filled_avg_price"])
                        if chk_data.get("filled_qty"):
                            filled_qty = float(chk_data["filled_qty"])

                if status not in terminal:
                    cancel_resp = await client.delete(f"{url}/{order_id}", headers=headers, timeout=5.0)
                    if cancel_resp.status_code not in (204, 404, 422):
                        _logger.warning("Could not cancel uncompleted Alpaca order %s: %s", order_id, cancel_resp.text)
                    await asyncio.sleep(0.25)
                    chk_resp = await client.get(f"{url}/{order_id}", headers=headers, timeout=5.0)
                    if chk_resp.status_code == 200:
                        chk_data = chk_resp.json()
                        status = (chk_data.get("status") or status).upper()
                        if chk_data.get("filled_avg_price"):
                            filled_price = float(chk_data["filled_avg_price"])
                        if chk_data.get("filled_qty"):
                            filled_qty = float(chk_data["filled_qty"])

                if status == "FILLED" and (not filled_price or not filled_qty):
                    # Never synthesize a fill price/quantity. Missing broker
                    # execution data is an indeterminate result that must be
                    # reconciled, not silently replaced by the quote/request.
                    status = "RECONCILIATION_REQUIRED"

                return OrderResult(
                    order_id=order_id,
                    status=status,
                    filled_price=safe_decimal(filled_price),
                    filled_quantity=safe_decimal(filled_qty),
                    message=f"Alpaca order status: {status}",
                )

        except Exception as e:
            _logger.exception("Alpaca order placement failed: %s", e)
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message="Broker order request failed. Review server logs and reconcile the broker account.",
            )

    async def cancel_order(self, order_id: str) -> bool:
        if self._mode == "live" and not is_live_trading_enabled():
            _logger.warning("Blocked live Alpaca order cancellation because ENABLE_LIVE_TRADING is disabled")
            return False
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/v2/orders/{order_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, headers=headers, timeout=5.0)
                return resp.status_code == 204
        except Exception as e:
            _logger.warning("Failed to cancel Alpaca order %s: %s", order_id, e)
            return False

    async def get_account_snapshot(self) -> dict[str, float | str | bool]:
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/v2/account"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "cash": float(data.get("cash") or 0.0),
                        "buying_power": float(data.get("buying_power") or 0.0),
                        "equity": float(data.get("equity") or data.get("portfolio_value") or 0.0),
                        "portfolio_value": float(data.get("portfolio_value") or data.get("equity") or 0.0),
                        "status": str(data.get("status") or ""),
                        "trading_blocked": bool(data.get("trading_blocked", False)),
                        "account_blocked": bool(data.get("account_blocked", False)),
                    }
                _logger.warning("Alpaca account request failed with HTTP %s", resp.status_code)
            return {}
        except Exception as e:
            _logger.warning("Failed to get Alpaca account snapshot: %s", e)
            return {}

    async def get_balance(self) -> float:
        snapshot = await self.get_account_snapshot()
        return float(snapshot.get("cash") or 0.0)

    async def get_positions(self) -> dict[str, dict]:
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/v2/positions"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    res = {}
                    for pos in data:
                        symbol = pos["symbol"].upper()
                        qty = float(pos.get("qty") or 0.0)
                        side = str(pos.get("side") or ("short" if qty < 0 else "long")).lower()
                        res[symbol] = {
                            "ticker": symbol,
                            "quantity": abs(qty),
                            "signed_quantity": qty,
                            "side": side,
                            "avg_price": float(pos.get("avg_entry_price") or 0.0),
                            "current_price": float(pos.get("current_price") or 0.0),
                            "market_value": abs(float(pos.get("market_value") or 0.0)),
                            "unrealized_pnl": float(pos.get("unrealized_pl") or 0.0),
                        }
                    return res
            return {}
        except Exception as e:
            _logger.warning("Failed to get Alpaca positions: %s", e)
            return {}

    async def close(self) -> None:
        if getattr(self, "_is_local_db", False) and self._db is not None:
            await self._db.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
