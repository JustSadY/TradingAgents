"""Regression tests for durable analysis cancellation across queue modes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

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

    monkeypatch.setattr(analysis_service.runtime, "request_cancel", request_cancel)
    monkeypatch.setattr(analysis_service.runtime, "publish_cancel", publish_cancel)

    assert await analysis_service.cancel_analysis(task_id) is True
    assert calls == [("request", task_id), ("publish", task_id)]


async def test_queued_analysis_never_enters_graph_after_cancel_marker(monkeypatch):
    """A worker/background task beginning after Stop must terminate pre-graph."""
    _Emitter.instances.clear()
    graph_started = False

    async def is_cancelled(_task_id: str) -> bool:
        return True

    async def unexpected_graph(*_args, **_kwargs):
        nonlocal graph_started
        graph_started = True

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service.runtime, "is_cancelled", is_cancelled)
    monkeypatch.setattr(analysis_service.runtime, "complete", _noop)
    monkeypatch.setattr(analysis_service, "run_individual_analysis", unexpected_graph)

    with pytest.raises(asyncio.CancelledError):
        await analysis_service.run_analysis("AAPL", "2026-07-26", "stock", None, None, task_id="queued-stop")

    assert graph_started is False
    assert _Emitter.instances[0].errors == ["Analysis cancelled."]
    assert _Emitter.instances[0].closed is True


async def test_cancelled_incremental_update_rolls_back_before_terminal_write(monkeypatch):
    """Cancellation cleanup must not dereference an ORM row after a bad flush."""
    from backend.services.analysis import orchestrator

    class _Row:
        def __init__(self):
            self.id_accesses = 0

        @property
        def id(self) -> int:
            self.id_accesses += 1
            if self.id_accesses > 1:
                raise AssertionError("Cancellation cleanup must use the captured row id")
            return 42

    class _Db:
        def __init__(self):
            self.events: list[str] = []

        async def rollback(self) -> None:
            self.events.append("rollback")

    class _RunEmitter:
        task_id = "cancelled-flush"

        def __init__(self):
            self.errors: list[str] = []

        async def emit_status(self, **_kwargs) -> None:
            return None

        async def emit_error(self, message: str) -> None:
            self.errors.append(message)

    row = _Row()
    db = _Db()
    emitter = _RunEmitter()

    async def skeleton(*_args, **_kwargs):
        return row

    async def cancelled_settings(_db):
        raise asyncio.CancelledError

    async def mark_cancelled(mark_db, row_id: int) -> None:
        assert mark_db is db
        assert row_id == 42
        assert db.events == ["rollback"]
        db.events.append("mark_cancelled")

    monkeypatch.setattr(orchestrator, "create_skeleton_result", skeleton)
    monkeypatch.setattr(orchestrator, "get_system_settings", cancelled_settings)
    monkeypatch.setattr(orchestrator, "mark_as_cancelled", mark_cancelled)

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.run_individual_analysis("NVDA", "2026-07-28", "stock", None, db, emitter)

    assert row.id_accesses == 1
    assert db.events == ["rollback", "mark_cancelled"]
    assert emitter.errors == ["Analysis cancelled."]


async def test_cancelled_status_cleanup_does_not_mask_cancellation(monkeypatch):
    """A DB cleanup fault must propagate the original cancellation, not a failure."""
    from backend.services.analysis import orchestrator

    class _Row:
        id = 73

    class _Db:
        async def rollback(self) -> None:
            return None

    class _RunEmitter:
        task_id = "cancelled-cleanup-failure"

        async def emit_status(self, **_kwargs) -> None:
            return None

        async def emit_error(self, _message: str) -> None:
            return None

    async def skeleton(*_args, **_kwargs):
        return _Row()

    async def cancelled_settings(_db):
        raise asyncio.CancelledError

    async def broken_mark(*_args, **_kwargs) -> None:
        raise RuntimeError("database temporarily unavailable")

    monkeypatch.setattr(orchestrator, "create_skeleton_result", skeleton)
    monkeypatch.setattr(orchestrator, "get_system_settings", cancelled_settings)
    monkeypatch.setattr(orchestrator, "mark_as_cancelled", broken_mark)

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.run_individual_analysis("NVDA", "2026-07-28", "stock", None, _Db(), _RunEmitter())


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

    async def no_metadata(_task_id: str):
        return None

    monkeypatch.setattr(analysis_service.runtime, "metadata", no_metadata)
    monkeypatch.setattr(analysis_service.runtime, "register", _noop)
    monkeypatch.setattr(analysis_service.runtime, "is_cancelled", not_cancelled)
    monkeypatch.setattr(analysis_service.runtime, "complete", _noop)
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
    """The run is marked terminal and cleaned up, then CancelledError re-raises.

    Swallowing CancelledError would break asyncio cancellation and arq's
    shutdown handling, so the worker must record the terminal state and let the
    exception continue to propagate.
    """
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

    terminal: list[tuple[str, str]] = []

    async def mark_terminal(task_id, status, user_id=None):
        assert user_id is None
        terminal.append((task_id, status))

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(settings_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr(analysis_service, "run_analysis_task", cancelled_run)
    monkeypatch.setattr(worker, "_mark_analysis_terminal", mark_terminal)
    for name in ("clear_meta", "clear_owner", "clear_cancel_request"):
        monkeypatch.setattr(task_store, name, AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await worker.run_analysis_job({}, "AAPL", "2026-07-26", "stock", None, "worker-stop")

    assert terminal == [("worker-stop", "cancelled")]
    task_store.clear_cancel_request.assert_awaited_once()
