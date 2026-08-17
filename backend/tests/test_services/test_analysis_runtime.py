from __future__ import annotations

from pathlib import Path

from backend.analysis_runtime import AnalysisRuntime, AnalysisTaskMeta, AnalysisTaskStatus, LocalBackend
from backend.services import analysis_service


async def test_local_runtime_round_trips_typed_task_state():
    runtime = AnalysisRuntime(LocalBackend())
    meta = AnalysisTaskMeta(
        task_id="runtime-local",
        ticker="NVDA",
        trade_date="2026-08-17",
        asset_type="stock",
        user_id=7,
        status=AnalysisTaskStatus.QUEUED,
        started_at=123.5,
    )

    await runtime.register(meta)

    assert await runtime.metadata(meta.task_id) == meta
    assert await runtime.owner(meta.task_id) == 7
    assert await runtime.active_tasks(7) == [meta]

    await runtime.request_cancel(meta.task_id)
    assert await runtime.is_cancelled(meta.task_id) is True

    await runtime.complete(meta.task_id, user_id=7)
    assert await runtime.metadata(meta.task_id) is None
    assert await runtime.owner(meta.task_id) is None
    assert await runtime.is_cancelled(meta.task_id) is False


def test_runtime_does_not_reintroduce_task_store_compatibility_surface():
    legacy_names = {
        "set_meta",
        "get_meta",
        "touch_task",
        "clear_meta",
        "is_cancel_requested",
        "clear_cancel_request",
        "list_tasks_for_user",
        "get_owner",
    }

    assert legacy_names.isdisjoint(vars(AnalysisRuntime))


def test_analysis_service_no_longer_imports_task_store_directly():
    source = Path(analysis_service.__file__).read_text()

    assert "from backend.core import task_store" not in source
    assert "backend.core.task_store" not in source
    assert "get_analysis_runtime" in source
