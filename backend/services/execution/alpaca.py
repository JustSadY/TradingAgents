import asyncio
import logging
from decimal import Decimal

import httpx

import backend.bootstrap  # noqa: F401
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
        self._mode = mode  # "simulation" (for paper trading) or "live"

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
        """Get live price for ticker. Falls back to Yahoo Finance provider."""
        return await _get_price(ticker)

    async def place_order(self, request: OrderRequest) -> OrderResult:
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
            "side": request.action.lower(),  # "buy" or "sell"
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
                    err_msg = f"Alpaca API error {resp.status_code}: {resp.text}"
                    _logger.error(err_msg)
                    return OrderResult(
                        order_id="",
                        status="REJECTED",
                        filled_price=None,
                        filled_quantity=None,
                        message=err_msg,
                    )

                data = resp.json()
                order_id = data["id"]
                status = data["status"].upper()
                filled_price = None
                filled_qty = None
                if data.get("filled_avg_price"):
                    filled_price = float(data["filled_avg_price"])
                if data.get("filled_qty"):
                    filled_qty = float(data["filled_qty"])
                for _ in range(6):
                    if status in ("FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED", "EXPIRED"):
                        if filled_price:  # only break if we actually got the price/qty
                            break
                    await asyncio.sleep(0.5)
                    chk_resp = await client.get(f"{url}/{order_id}", headers=headers, timeout=5.0)
                    if chk_resp.status_code == 200:
                        chk_data = chk_resp.json()
                        status = chk_data["status"].upper()
                        if chk_data.get("filled_avg_price"):
                            filled_price = float(chk_data["filled_avg_price"])
                        if chk_data.get("filled_qty"):
                            filled_qty = float(chk_data["filled_qty"])
                if not filled_price and status == "FILLED":
                    chk_resp = await client.get(f"{url}/{order_id}", headers=headers, timeout=5.0)
                    if chk_resp.status_code == 200:
                        chk_data = chk_resp.json()
                        if chk_data.get("filled_avg_price"):
                            filled_price = float(chk_data["filled_avg_price"])
                        if chk_data.get("filled_qty"):
                            filled_qty = float(chk_data["filled_qty"])
                if status == "FILLED" and not filled_price:
                    filled_price = request.reference_price
                    filled_qty = request.quantity

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
                message=str(e),
            )

    async def cancel_order(self, order_id: str) -> bool:
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/v2/orders/{order_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, headers=headers, timeout=5.0)
                return resp.status_code == 204
        except Exception as e:
            _logger.warning("Failed to cancel Alpaca order %s: %s", order_id, e)
            return False

    async def get_balance(self) -> float:
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/v2/account"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("cash", 0.0))
            return 0.0
        except Exception as e:
            _logger.warning("Failed to get Alpaca account balance: %s", e)
            return 0.0

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
                        res[symbol] = {
                            "ticker": symbol,
                            "quantity": float(pos["qty"]),
                            "avg_price": float(pos["avg_entry_price"]),
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
