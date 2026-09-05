from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.execution.base import OrderResult


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Emitter:
    def __init__(self, task_id: str):
        self.task_id = task_id

    async def close(self):
        return None


def _completed_row():
    return SimpleNamespace(
        id=41,
        signal="Buy",
        quality={"confidence": "high"},
        chart_annotations=None,
        portfolio_decision_json={"rating": "Buy", "position_size_pct": 5},
        decision_transition_json=None,
        strategy_update_status="applied",
        analysis_mode="live",
        learning_eligible=True,
        final_decision="Buy",
    )


async def _run_cancel_during_order(monkeypatch, *, external_submission: bool):
    from backend.services import analysis_service

    session = _Session()
    entered = asyncio.Event()
    release = asyncio.Event()
    emitted = AsyncMock()
    cleared = AsyncMock()

    async def run_analysis(*_args, **_kwargs):
        return "task-order-cancel", _completed_row()

    async def place_order(*_args, **_kwargs):
        entered.set()
        await release.wait()
        return OrderResult(
            order_id="broker-1" if external_submission else "sim-1",
            status="FILLED",
            filled_price=Decimal("100"),
            filled_quantity=Decimal("1"),
            external_submission=external_submission,
        )

    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service, "run_analysis", run_analysis)
    monkeypatch.setattr(analysis_service, "auto_execute_signals_enabled", lambda _settings: True)
    monkeypatch.setattr(analysis_service, "place_signal_order", place_order)
    monkeypatch.setattr(analysis_service, "_emit_auto_order_result", emitted)
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", cleared)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", AsyncMock(return_value=False))

    task = asyncio.create_task(
        analysis_service.run_analysis_task(
            "NVDA",
            "2026-09-05",
            "stock",
            SimpleNamespace(auto_execute_signals=True),
            "task-order-cancel",
        )
    )
    await entered.wait()
    task.cancel()
    release.set()
    await task

    return session, emitted, cleared


@pytest.mark.asyncio
async def test_cancellation_after_external_submission_preserves_broker_result(monkeypatch):
    session, emitted, cleared = await _run_cancel_during_order(monkeypatch, external_submission=True)

    # One commit persists the completed analysis, the second preserves the
    # irreversible broker audit/result after cancellation arrived too late.
    assert session.commits == 2
    assert session.rollbacks == 0
    kwargs = emitted.await_args.kwargs
    assert kwargs["result"].external_submission is True
    assert kwargs["result"].status == "FILLED"
    assert "broker outcome was retained" in kwargs["message"]
    cleared.assert_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_simulation_order_rolls_back_local_mutation(monkeypatch):
    session, emitted, cleared = await _run_cancel_during_order(monkeypatch, external_submission=False)

    # The analysis itself stays committed, but the simulated order transaction
    # is local-only and remains honestly rollback-able.
    assert session.commits == 1
    assert session.rollbacks == 1
    kwargs = emitted.await_args.kwargs
    assert kwargs["outcome"] == "skipped"
    assert kwargs["reason_code"] == "cancelled"
    assert "before the automatic order was committed" in kwargs["message"]
    cleared.assert_awaited()
