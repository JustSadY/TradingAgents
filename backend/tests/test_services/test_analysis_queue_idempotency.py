import asyncio
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_worker_dispatch_uses_analysis_task_id_as_arq_job_id(monkeypatch):
    from backend.services import analysis_queue

    calls = []

    class Pool:
        async def enqueue_job(self, *args, **kwargs):
            calls.append((args, kwargs))

    async def get_pool():
        return Pool()

    monkeypatch.setattr(analysis_queue, "queue_mode", lambda: "worker")
    monkeypatch.setattr(analysis_queue, "get_arq_pool", get_pool)

    await analysis_queue.dispatch_analysis(
        None,
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        settings=object(),
        task_id="analysis-task-123",
        user=SimpleNamespace(id=7),
        triggered_by="alert",
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("run_analysis_job", "NVDA", "2026-09-05", "stock", 7, "analysis-task-123", "alert")
    assert kwargs == {"_job_id": "analysis-task-123"}


@pytest.mark.asyncio
async def test_direct_inline_dispatch_deduplicates_running_task_id(monkeypatch):
    from backend.services import analysis_queue, analysis_service

    started = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def run_analysis_task(*args, **kwargs):
        nonlocal started
        started += 1
        entered.set()
        await release.wait()

    monkeypatch.setattr(analysis_queue, "queue_mode", lambda: "inline")
    monkeypatch.setattr(analysis_service, "run_analysis_task", run_analysis_task)
    analysis_queue._INLINE_ANALYSIS_TASKS.clear()
    analysis_queue._INLINE_TASKS.clear()

    kwargs = dict(
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        settings=object(),
        task_id="same-task",
        user=SimpleNamespace(id=7),
        triggered_by="alert",
    )

    await analysis_queue.dispatch_analysis(None, **kwargs)
    await entered.wait()
    await analysis_queue.dispatch_analysis(None, **kwargs)

    assert started == 1
    assert len(analysis_queue._INLINE_ANALYSIS_TASKS) == 1

    release.set()
    running = list(analysis_queue._INLINE_TASKS)
    if running:
        await asyncio.gather(*running)
    await asyncio.sleep(0)

    assert "same-task" not in analysis_queue._INLINE_ANALYSIS_TASKS
