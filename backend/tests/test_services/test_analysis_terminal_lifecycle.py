"""Regression coverage for analysis terminal event and task ownership ordering."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.services import analysis_service


class _Emitter:
    events: list[str] = []

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    async def emit_error(self, _message: str) -> None:
        self.events.append("error")

    async def close(self) -> None:
        self.events.append("close")


async def test_deferred_run_keeps_owner_and_socket_until_background_runner_finalizes(monkeypatch):
    """The post-graph commit/order window must remain cancellable."""
    task_id = "deferred-terminal-lifecycle"
    _Emitter.events.clear()
    cleared_owners: list[str] = []

    async def not_cancelled(_task_id: str) -> bool:
        return False

    async def fake_track(task_id: str, **_kwargs) -> None:
        current = asyncio.current_task()
        assert current is not None
        analysis_service._RUNNING_TASKS[task_id] = current
        analysis_service._TASK_REGISTRY[task_id] = {"user_id": None}
        analysis_service._TASK_OWNERS[task_id] = None

    async def completed_graph(*_args, **_kwargs):
        return task_id, SimpleNamespace(id=1)

    async def clear_owner(value: str) -> None:
        cleared_owners.append(value)

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service, "_track_running_task", fake_track)
    monkeypatch.setattr(analysis_service, "run_individual_analysis", completed_graph)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service.task_store, "clear_owner", clear_owner)

    try:
        await analysis_service.run_analysis(
            "NVDA", "2026-07-28", "stock", None, object(), task_id=task_id, defer_terminal_cleanup=True
        )

        assert task_id in analysis_service._RUNNING_TASKS
        assert task_id in analysis_service._TASK_REGISTRY
        assert task_id in analysis_service._TASK_OWNERS
        assert cleared_owners == []
        assert _Emitter.events == []
    finally:
        analysis_service._RUNNING_TASKS.pop(task_id, None)
        analysis_service._TASK_REGISTRY.pop(task_id, None)
        analysis_service._TASK_OWNERS.pop(task_id, None)


async def test_cancel_marker_emits_terminal_error_before_deferred_socket_close(monkeypatch):
    """A cancelled DB flush must not close the WS before its error event."""
    task_id = "cancel-terminal-order"
    timeline: list[str] = []

    class _TimelineEmitter:
        def __init__(self, task_id: str) -> None:
            self.task_id = task_id

        async def emit_error(self, _message: str) -> None:
            timeline.append("error")

        async def close(self) -> None:
            timeline.append("close")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def rollback(self) -> None:
            timeline.append("rollback")

    async def failed_run(*_args, **kwargs):
        assert kwargs["defer_terminal_cleanup"] is True
        raise RuntimeError("flush was interrupted")

    async def cancelled(_task_id: str) -> bool:
        return True

    async def terminalize(*_args, **_kwargs) -> bool:
        timeline.append("clear")
        return True

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _TimelineEmitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(analysis_service, "run_analysis", failed_run)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", cancelled)
    monkeypatch.setattr(analysis_service, "terminalize_task", terminalize)

    await analysis_service.run_analysis_task("NVDA", "2026-07-28", "stock", None, task_id)

    assert timeline == ["rollback", "error", "clear", "close"]


async def test_terminal_orchestrator_error_is_not_retried(monkeypatch):
    """Never launch a retry after the inner run may have told the UI it failed."""
    task_id = "terminal-error-no-retry"
    _Emitter.events.clear()
    retry_calls = 0
    cleared = 0

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    async def not_cancelled(_task_id: str) -> bool:
        return False

    async def terminal_error(*_args, **kwargs):
        assert kwargs["defer_terminal_cleanup"] is True
        error = RuntimeError("model failed")
        error._analysis_terminal_event_emitted = True
        raise error

    async def retry(*_args, **_kwargs) -> bool:
        nonlocal retry_calls
        retry_calls += 1
        return True

    async def terminalize(*_args, **_kwargs) -> bool:
        nonlocal cleared
        cleared += 1
        return True

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(analysis_service, "run_analysis", terminal_error)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "_maybe_retry_analysis", retry)
    monkeypatch.setattr(analysis_service, "terminalize_task", terminalize)

    await analysis_service.run_analysis_task("NVDA", "2026-07-28", "stock", None, task_id)

    assert retry_calls == 0
    assert cleared == 1
    assert _Emitter.events == ["close"]


async def test_unscheduled_retry_clears_tracking_and_sends_terminal_error(monkeypatch):
    """A retry-budget/enqueue failure cannot leave a ghost active task behind."""
    task_id = "retry-terminal-cleanup"
    _Emitter.events.clear()
    cleared = 0

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    async def not_cancelled(_task_id: str) -> bool:
        return False

    async def pre_graph_failure(*_args, **kwargs):
        assert kwargs["defer_terminal_cleanup"] is True
        raise RuntimeError("task registry unavailable")

    async def retry_exhausted(*_args, **_kwargs) -> bool:
        return False

    async def terminalize(*_args, **_kwargs) -> bool:
        nonlocal cleared
        cleared += 1
        return True

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", _Emitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(analysis_service, "run_analysis", pre_graph_failure)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "_maybe_retry_analysis", retry_exhausted)
    monkeypatch.setattr(analysis_service, "terminalize_task", terminalize)

    await analysis_service.run_analysis_task("NVDA", "2026-07-28", "stock", None, task_id)

    assert cleared == 1
    assert _Emitter.events == ["error", "close"]
