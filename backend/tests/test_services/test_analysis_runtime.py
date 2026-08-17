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


async def test_runtime_compatibility_payload_uses_typed_model_validation():
    runtime = AnalysisRuntime(LocalBackend())
    payload = {
        "ticker": "AAPL",
        "trade_date": "2026-08-17",
        "asset_type": "stock",
        "user_id": 3,
        "status": "running",
        "started_at": 42.0,
        "retry_count": 1,
    }

    await runtime.set_meta("compat-task", payload)

    assert await runtime.get_meta("compat-task") == payload


def test_analysis_service_no_longer_imports_task_store_directly():
    source = Path(analysis_service.__file__).read_text()

    assert "from backend.core import task_store" not in source
    assert "backend.core.task_store" not in source
    assert "get_analysis_runtime" in source
