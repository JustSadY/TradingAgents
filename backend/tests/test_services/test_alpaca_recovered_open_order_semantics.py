from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest


def _request() -> OrderRequest:
    return OrderRequest(
        ticker="NVDA",
        action="BUY",
        quantity=Decimal("1"),
        reference_price=Decimal("100"),
        analysis_id=42,
    )


@pytest.mark.asyncio
async def test_recovered_open_submission_is_canceled_and_rechecked(monkeypatch):
    from backend.services import execution
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        canceled = None

        def submit_order(self, _request):
            raise TimeoutError("submit response lost")

        def get_order_by_client_id(self, _client_order_id):
            return SimpleNamespace(
                id="alpaca-recovered-1",
                status="NEW",
                filled_avg_price=None,
                filled_qty="0",
            )

        def cancel_order_by_id(self, order_id):
            self.canceled = order_id

        def get_order_by_id(self, order_id):
            assert order_id == "alpaca-recovered-1"
            return SimpleNamespace(
                id=order_id,
                status="CANCELED",
                filled_avg_price=None,
                filled_qty="0",
            )

    trading = Trading()
    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return trading, object()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(trader, "_clients", clients)
    monkeypatch.setattr(execution.alpaca.asyncio, "sleep", no_sleep)

    result = await trader.place_order(_request())

    assert trading.canceled == "alpaca-recovered-1"
    assert result.order_id == "alpaca-recovered-1"
    assert result.status == "CANCELED"
    assert result.external_submission is True


@pytest.mark.asyncio
async def test_recovered_order_still_open_after_cancel_requires_reconciliation(monkeypatch):
    from backend.services import execution
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        cancel_calls = 0

        def submit_order(self, _request):
            raise TimeoutError("submit response lost")

        def get_order_by_client_id(self, _client_order_id):
            return SimpleNamespace(
                id="alpaca-recovered-open",
                status="NEW",
                filled_avg_price=None,
                filled_qty="0",
            )

        def cancel_order_by_id(self, _order_id):
            self.cancel_calls += 1

        def get_order_by_id(self, order_id):
            return SimpleNamespace(
                id=order_id,
                status="NEW",
                filled_avg_price=None,
                filled_qty="0",
            )

    trading = Trading()
    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return trading, object()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(trader, "_clients", clients)
    monkeypatch.setattr(execution.alpaca.asyncio, "sleep", no_sleep)

    result = await trader.place_order(_request())

    assert trading.cancel_calls == 1
    assert result.order_id == "alpaca-recovered-open"
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_order_still_open"
    assert result.external_submission is True


@pytest.mark.asyncio
async def test_recovered_identity_and_fill_survive_cleanup_network_failure(monkeypatch):
    from backend.services import execution
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def submit_order(self, _request):
            raise TimeoutError("submit response lost")

        def get_order_by_client_id(self, _client_order_id):
            return SimpleNamespace(
                id="alpaca-recovered-partial",
                status="PARTIALLY_FILLED",
                filled_avg_price="100",
                filled_qty="0.25",
            )

        def cancel_order_by_id(self, _order_id):
            return None

        def get_order_by_id(self, _order_id):
            raise TimeoutError("cleanup poll unavailable")

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(trader, "_clients", clients)
    monkeypatch.setattr(execution.alpaca.asyncio, "sleep", no_sleep)

    result = await trader.place_order(_request())

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_submission_uncertain"
    assert result.order_id == "alpaca-recovered-partial"
    assert result.filled_price == Decimal("100")
    assert result.filled_quantity == Decimal("0.25")
    assert result.external_submission is True
