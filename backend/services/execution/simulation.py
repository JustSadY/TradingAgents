import logging

import backend.bootstrap  # noqa: F401  (sets engine env before importing the engine)
from backend.core.database import AsyncSessionLocal
from backend.services.market_data_service import get_live_price as _get_price
from backend.services.mock_trading_service import (
    execute_order,
    get_or_create_sim_portfolio,
    get_portfolio_with_live_prices,
)

from .base import BaseTraderInterface, OrderRequest, OrderResult

_logger = logging.getLogger(__name__)


class SimulationTrader(BaseTraderInterface):
    def __init__(self, portfolio_id: int = 1, initial_capital: float = 100_000.0, db=None):
        if db is None:
            db = AsyncSessionLocal()
        self._db = db
        self._portfolio_id = portfolio_id
        self._initial_capital = initial_capital

    @property
    def mode(self) -> str:
        return "simulation"

    @property
    def broker_name(self) -> str:
        return "simulation"

    async def get_current_price(self, ticker: str) -> float | None:
        return await _get_price(ticker)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            res = await execute_order(
                db=self._db,
                ticker=request.ticker,
                action=request.action,
                quantity=request.quantity,
                portfolio_id=self._portfolio_id,
                leverage=getattr(request, "leverage", 1.0),
                stop_loss=getattr(request, "stop_loss", None),
                take_profit=getattr(request, "take_profit", None),
                allow_short=getattr(request, "allow_short", False),
            )
            return OrderResult(
                order_id=str(res["order_id"]),
                status=res["status"],
                filled_price=res["price"],
                filled_quantity=res["quantity"],
                commission=res["commission"],
                message="Simulation order filled",
            )
        except Exception as e:
            _logger.exception("Simulation order failed for %s", request.ticker)
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_quantity=None,
                message=str(e),
            )

    async def cancel_order(self, order_id: str) -> bool:
        return False

    async def get_balance(self) -> float:
        portfolio = await get_or_create_sim_portfolio(
            self._db, initial_capital=self._initial_capital, portfolio_id=self._portfolio_id
        )
        return portfolio.cash_available

    async def get_positions(self) -> dict[str, dict]:
        portfolio_data = await get_portfolio_with_live_prices(self._db, portfolio_id=self._portfolio_id)
        res = {}
        for h in portfolio_data.get("holdings", []):
            res[h["ticker"]] = {
                "ticker": h["ticker"],
                "quantity": h["quantity"],
                "avg_price": h["avg_buy_price"],
            }
        return res
