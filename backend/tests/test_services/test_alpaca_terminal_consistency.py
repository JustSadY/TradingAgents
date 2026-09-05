from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest


def _request(**overrides) -> OrderRequest:
    values = {
        "ticker": "NVDA",
        "action": "BUY",
        "quantity": Decimal("1"),
        "reference_price": Decimal("100"),
        "analysis_id": 501,
    }
    values.update(overrides)
    return OrderRequest(**values)


@pytest.mark.asyncio
async def test_rejected_order_with_positive_fill_requires_reconciliation(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def submit_order(self, _request):
            return SimpleNamespace(
                id="alpaca-conflict-1",
                status="REJECTED",
                filled_avg_price="100",
                filled_qty="0.5",
            )

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_request())

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_status_fill_conflict"
    assert result.order_id == "alpaca-conflict-1"
    assert result.filled_quantity == Decimal("0.5")
    assert result.filled_price == Decimal("100")


@pytest.mark.asyncio
async def test_missing_submit_order_id_is_recovered_by_client_reference(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        client_order_id = None

        def submit_order(self, broker_request):
            self.client_order_id = broker_request.client_order_id
            return SimpleNamespace(
                id=None,
                status="FILLED",
                filled_avg_price="100",
                filled_qty="1",
            )

        def get_order_by_client_id(self, client_order_id):
            assert client_order_id == self.client_order_id
            return SimpleNamespace(
                id="alpaca-recovered-id",
                status="FILLED",
                filled_avg_price="100",
                filled_qty="1",
            )

    trading = Trading()
    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return trading, object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_request())

    assert result.status == "FILLED"
    assert result.order_id == "alpaca-recovered-id"
    assert result.external_submission is True
