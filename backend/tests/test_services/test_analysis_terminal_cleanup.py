from __future__ import annotations

import asyncio

from backend.services import analysis_service
from backend.services.analysis.task_lifecycle import AnalysisTaskStatus, TerminalResult


async def test_terminalize_task_cleans_local_and_shared_state_once(monkeypatch):
    task_id = "terminalize-once-regression"
    user_id = 17
    calls: list[tuple[str, object]] = []
    heartbeat_waiter = asyncio.Event()
    heartbeat = asyncio.create_task(heartbeat_waiter.wait())
    current = asyncio.current_task()
    assert current is not None

    async def complete(value: str, owner: int | None = None) -> None:
        calls.append(("complete", (value, owner)))

    monkeypatch.setattr(analysis_service.runtime, "complete", complete)

    analysis_service._TERMINAL_COORDINATOR.reset(task_id)
    analysis_service._RUNNING_TASKS[task_id] = current
    analysis_service._TASK_REGISTRY[task_id] = {"user_id": user_id}
    analysis_service._TASK_OWNERS[task_id] = user_id
    analysis_service._HEARTBEAT_TASKS[task_id] = heartbeat

    result = TerminalResult(AnalysisTaskStatus.COMPLETED)
    try:
        assert await analysis_service.terminalize_task(task_id, user_id, result) is True
        assert await analysis_service.terminalize_task(task_id, user_id, result) is False

        assert task_id not in analysis_service._RUNNING_TASKS
        assert task_id not in analysis_service._TASK_REGISTRY
        assert task_id not in analysis_service._TASK_OWNERS
        assert task_id not in analysis_service._HEARTBEAT_TASKS
        assert heartbeat.cancelled()
        assert calls == [("complete", (task_id, user_id))]
        assert analysis_service.get_terminal_result(task_id) == result
    finally:
        analysis_service._RUNNING_TASKS.pop(task_id, None)
        analysis_service._TASK_REGISTRY.pop(task_id, None)
        analysis_service._TASK_OWNERS.pop(task_id, None)
        extra_heartbeat = analysis_service._HEARTBEAT_TASKS.pop(task_id, None)
        if extra_heartbeat:
            extra_heartbeat.cancel()
