from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_terminal_cancel_with_fill_emits_partial_fill(monkeypatch):
    from backend.services.analysis import emitter as emitter_module

    events: list[dict] = []

    async def publish_event(_task_id: str, event: dict) -> None:
        events.append(event)

    monkeypatch.setattr(emitter_module, "publish_event", publish_event)
    emitter = emitter_module.AnalysisEmitter("partial-fill")

    await emitter.emit_order_result(
        analysis_id=42,
        ticker="NVDA",
        action="BUY",
        signal="Buy",
        outcome="rejected",
        broker_status="CANCELED",
        order_id="broker-42",
        filled_quantity=Decimal("2"),
        filled_price=Decimal("100"),
    )

    assert events[0]["outcome"] == "partially_filled"
    assert events[0]["status"] == "partially_filled"
    assert events[0]["filled_quantity"] == 2.0
    assert events[0]["filled_price"] == 100.0


@pytest.mark.asyncio
async def test_reconciliation_status_takes_precedence_over_fill_shape(monkeypatch):
    from backend.services.analysis import emitter as emitter_module

    events: list[dict] = []

    async def publish_event(_task_id: str, event: dict) -> None:
        events.append(event)

    monkeypatch.setattr(emitter_module, "publish_event", publish_event)
    emitter = emitter_module.AnalysisEmitter("reconciliation")

    await emitter.emit_order_result(
        analysis_id=43,
        ticker="NVDA",
        action="BUY",
        signal="Buy",
        outcome="rejected",
        broker_status="RECONCILIATION_REQUIRED",
        filled_quantity=Decimal("2"),
    )

    assert events[0]["outcome"] == "reconciliation_required"
    assert events[0]["status"] == "reconciliation_required"
