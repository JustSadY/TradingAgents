"""Regression tests for durable analysis cancellation across queue modes."""

from __future__ import annotations

import asyncio

import pytest

from backend.core import task_store
from backend.services import analysis_service


async def _noop(*_args, **_kwargs) -> None:
    return None


class _Emitter:
    instances: list[_Emitter] = []

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.errors: list[str] = []
        self.closed = False
        self.instances.append(self)

    async def emit_error(self, message: str) -> None:
        self.errors.append(message)

    async def close(self) -> None:
        self.closed = True


async def test_cancel_marker_survives_without_redis(monkeypatch):
    """Inline BackgroundTasks need a local durable intent marker as well."""
    task_id = "local-marker-regression"
    monkeypatch.setattr(task_store, "redis_enabled", lambda: False)
    await task_store.clear_cancel_request(task_id)
    try:
        await task_store.request_cancel(task_id)
        assert await task_store.is_cancel_requested(task_id) is True
    finally:
        await task_store.clear_cancel_request(task_id)


async def test_cancel_local_task_keeps_tracking_until_runner_acknowledges():
    """A queued/start race must not erase the record before the task stops."""
    task_id = "cancel-local-regression"
    waiter = asyncio.Event()
    task = asyncio.create_task(waiter.wait())
    await asyncio.sleep(0)
    analysis_service._RUNNING_TASKS[task_id] = task
    analysis_service._TASK_REGISTRY[task_id] = {"user_id": 7}
    analysis_service._TASK_OWNERS[task_id] = 7

    try:
        assert await analysis_service.cancel_local_task(task_id) is True
        assert analysis_service._RUNNING_TASKS[task_id] is task
        assert analysis_service._TASK_REGISTRY[task_id] == {"user_id": 7}
        assert analysis_service._TASK_OWNERS[task_id] == 7
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        analysis_service._RUNNING_TASKS.pop(task_id, None)
        analysis_service._TASK_REGISTRY.pop(task_id, None)
        analysis_service._TASK_OWNERS.pop(task_id, None)


async def test_cancel_analysis_persists_intent_before_publish(monkeypatch):
    task_id = "queued-cancel-regression"
    calls: list[tuple[str, str]] = []

    async def request_cancel(value: str) -> None:
        calls.append(("request", value))

    async def publish_cancel(value: str) -> None:
        calls.append(("publish", value))

    monkeypatch.setattr(analysis_service.task_store, "request_cancel", request_cancel)
    monkeypatch.setattr(analysis_service.task_store, "publish_cancel", publish_cancel)

    assert await analysis_service.cancel_analysis(task_id) is True
    assert calls == [("request", task_id), ("publish", task_id)]


async def test_queued_analysis_never_enters_graph_after_cancel_marker(monkeypatch):
    """A worker/background task beginning after Stop must terminate pre-graph."""
    _Emitter.instances.clear()
    graph_started = False

    async def is_cancel_requested(_task_id: str) -> bool:
        return True

    async def unexpected_graph(*_args, **_kwargs):
        nonlocal graph_started
        graph_started = True

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", is_cancel_requested)
    monkeypatch.setattr(analysis_service.task_store, "clear_owner", _noop)
    monkeypatch.setattr(analysis_service, "run_individual_analysis", unexpected_graph)

    with pytest.raises(asyncio.CancelledError):
        await analysis_service.run_analysis("AAPL", "2026-07-26", "stock", None, None, task_id="queued-stop")

    assert graph_started is False
    assert _Emitter.instances[0].errors == ["Analysis cancelled."]
    assert _Emitter.instances[0].closed is True


async def test_portfolio_parent_is_registered_and_cancelled_with_children(monkeypatch):
    """Portfolio jobs need the same parent registry lifecycle as single runs."""
    task_id = "portfolio-cancel-regression"
    entered = asyncio.Event()
    waiting = asyncio.Event()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self) -> None:
            return None

    async def run_portfolio(*_args, **_kwargs):
        entered.set()
        await waiting.wait()

    async def not_cancelled(_task_id: str) -> bool:
        return False

    for name in ("get_meta", "set_meta", "set_owner", "clear_meta", "clear_owner", "clear_cancel_request"):
        monkeypatch.setattr(analysis_service.task_store, name, _noop)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(analysis_service, "run_portfolio_analysis", run_portfolio)
    monkeypatch.setattr(analysis_service, "_emit_cancelled_task", _noop)

    task = asyncio.create_task(
        analysis_service.run_portfolio_task(["AAPL", "MSFT"], "2026-07-26", "stock", None, task_id=task_id)
    )
    try:
        await entered.wait()
        assert analysis_service._RUNNING_TASKS[task_id] is task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task_id not in analysis_service._RUNNING_TASKS
        assert task_id not in analysis_service._TASK_REGISTRY
    finally:
        if not task.done():
            task.cancel()
        analysis_service._RUNNING_TASKS.pop(task_id, None)
        analysis_service._TASK_REGISTRY.pop(task_id, None)
        analysis_service._TASK_OWNERS.pop(task_id, None)


async def test_worker_treats_cancelled_analysis_as_terminal(monkeypatch):
    """ARQ must see a normal return instead of requeueing CancelledError."""
    from backend import worker
    from backend.core import database
    from backend.services import settings_service

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self) -> None:
            return None

    async def get_settings(*_args, **_kwargs):
        return object()

    async def cancelled_run(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(settings_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr(analysis_service, "run_analysis_task", cancelled_run)

    assert await worker.run_analysis_job({}, "AAPL", "2026-07-26", "stock", None, "worker-stop") is None
