from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.analysis_service import _canonical_order_signal, _emit_auto_order_result
from backend.services.execution.base import OrderResult


def test_canonical_order_signal_prefers_structured_portfolio_rating():
    row = SimpleNamespace(
        signal="Sell",
        portfolio_decision_json={"rating": "Buy"},
    )

    assert _canonical_order_signal(row) == "Buy"


def test_canonical_order_signal_reads_json_and_falls_back_to_persisted_signal():
    structured = SimpleNamespace(
        signal="Sell",
        portfolio_decision_json='{"rating": "Overweight"}',
    )
    malformed = SimpleNamespace(
        signal="Underweight",
        portfolio_decision_json="not-json",
    )

    assert _canonical_order_signal(structured) == "Overweight"
    assert _canonical_order_signal(malformed) == "Underweight"


@pytest.mark.asyncio
async def test_auto_order_event_uses_same_canonical_rating_as_execution():
    emitted = {}

    class Emitter:
        async def emit_order_result(self, **payload):
            emitted.update(payload)

    row = SimpleNamespace(
        id=42,
        signal="Sell",
        portfolio_decision_json={"rating": "Buy"},
    )
    result = OrderResult(
        order_id="alpaca-42",
        status="FILLED",
        filled_price=100,
        filled_quantity=1,
        message="filled",
    )

    await _emit_auto_order_result(
        Emitter(),
        row=row,
        ticker="NVDA",
        result=result,
    )

    assert emitted["signal"] == "Buy"
    assert emitted["action"] == "BUY"
    assert emitted["outcome"] == "filled"
    assert emitted["order_id"] == "alpaca-42"
