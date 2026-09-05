from decimal import Decimal

import pytest

from backend.services.execution.base import OrderRequest


class _Db:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_simulation_price_releases_db_when_enabled(monkeypatch):
    from backend.services.execution import simulation

    db = _Db()

    async def get_price(ticker: str):
        assert ticker == "NVDA"
        assert db.commits == 1
        return 100.0

    monkeypatch.setattr(simulation, "_get_price", get_price)
    trader = simulation.SimulationTrader(db=db, release_db_before_network=True)

    assert await trader.get_current_price("NVDA") == 100.0
    assert db.commits == 1


@pytest.mark.asyncio
async def test_simulation_order_forwards_price_io_release_to_execution_service(monkeypatch):
    from backend.services.execution import simulation

    captured = {}

    async def execute_order(**kwargs):
        captured.update(kwargs)
        return {
            "order_id": 9,
            "status": "FILLED",
            "price": 100,
            "quantity": 1,
            "commission": 0.1,
        }

    monkeypatch.setattr(simulation, "execute_order", execute_order)
    trader = simulation.SimulationTrader(db=_Db(), release_db_before_network=True)

    result = await trader.place_order(
        OrderRequest(
            ticker="NVDA",
            action="BUY",
            quantity=Decimal("1"),
            reference_price=Decimal("100"),
        )
    )

    assert captured["release_before_price_io"] is True
    assert result.status == "FILLED"
    assert result.external_submission is False


def test_execution_factory_enables_simulation_network_boundary():
    from backend.services.execution.factory import get_trader

    trader = get_trader(mode="simulation", broker="simulation", db=object())

    assert trader._release_db_before_network is True


def test_direct_simulation_trader_keeps_manual_transaction_control_by_default():
    from backend.services.execution.simulation import SimulationTrader

    trader = SimulationTrader(db=object())

    assert trader._release_db_before_network is False
