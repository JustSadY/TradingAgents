import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select


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
        triggered_by="manual",
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("run_analysis_job", "NVDA", "2026-09-05", "stock", 7, "analysis-task-123", "manual")
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
        triggered_by="manual",
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


@pytest.mark.asyncio
async def test_alert_dispatch_reuses_one_durable_analysis_identity(monkeypatch, db, test_user):
    from backend.core import database
    from backend.models.analysis import AnalysisResult
    from backend.services import analysis_queue, analysis_service

    first = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        task_id="random-first",
        status="queued",
        triggered_by="alert",
    )
    db.add(first)
    await db.flush()

    @asynccontextmanager
    async def same_session():
        yield db

    discard = AsyncMock()
    register = AsyncMock()
    monkeypatch.setattr(database, "AsyncSessionLocal", same_session)
    monkeypatch.setattr(analysis_service, "discard_queued_task", discard)
    monkeypatch.setattr(analysis_service, "register_queued_task", register)

    stable_task_id, should_dispatch = await analysis_queue._prepare_alert_dispatch_identity(
        task_id="random-first",
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        user=test_user,
    )

    assert should_dispatch is True
    assert stable_task_id == analysis_queue._alert_task_id(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
    )
    assert first.task_id == stable_task_id
    discard.assert_awaited_once_with("random-first", test_user.id)
    register.assert_awaited_once_with(
        stable_task_id,
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        user_id=test_user.id,
    )

    duplicate = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        task_id="random-retry",
        status="queued",
        triggered_by="alert",
    )
    db.add(duplicate)
    await db.flush()
    discard.reset_mock()
    register.reset_mock()

    retry_task_id, retry_should_dispatch = await analysis_queue._prepare_alert_dispatch_identity(
        task_id="random-retry",
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        user=test_user,
    )

    assert retry_task_id == stable_task_id
    assert retry_should_dispatch is False
    rows = list(
        (
            await db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.user_id == test_user.id,
                    AnalysisResult.ticker == "NVDA",
                    AnalysisResult.trade_date == "2026-09-05",
                    AnalysisResult.triggered_by == "alert",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [row.id for row in rows] == [first.id]
    discard.assert_awaited_once_with("random-retry", test_user.id)
    register.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_dispatch_without_its_staged_row_never_relaunches_canonical_job(monkeypatch, db, test_user):
    from backend.core import database
    from backend.models.analysis import AnalysisResult
    from backend.services import analysis_queue, analysis_service

    stable_task_id = analysis_queue._alert_task_id(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
    )
    db.add(
        AnalysisResult(
            user_id=test_user.id,
            ticker="NVDA",
            trade_date="2026-09-05",
            asset_type="stock",
            task_id=stable_task_id,
            status="completed",
            triggered_by="alert",
        )
    )
    await db.flush()

    @asynccontextmanager
    async def same_session():
        yield db

    discard = AsyncMock()
    register = AsyncMock()
    monkeypatch.setattr(database, "AsyncSessionLocal", same_session)
    monkeypatch.setattr(analysis_service, "discard_queued_task", discard)
    monkeypatch.setattr(analysis_service, "register_queued_task", register)

    resolved, should_dispatch = await analysis_queue._prepare_alert_dispatch_identity(
        task_id="missing-random-staged-row",
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        user=test_user,
    )

    assert resolved == stable_task_id
    assert should_dispatch is False
    discard.assert_awaited_once_with("missing-random-staged-row", test_user.id)
    register.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_alert_queue_submission_removes_unowned_queued_row(monkeypatch, db, test_user):
    from backend.core import database
    from backend.models.analysis import AnalysisResult
    from backend.services import analysis_queue, analysis_service

    stable_task_id = analysis_queue._alert_task_id(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
    )
    row = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-09-05",
        asset_type="stock",
        task_id=stable_task_id,
        status="queued",
        triggered_by="alert",
    )
    db.add(row)
    await db.flush()

    @asynccontextmanager
    async def same_session():
        yield db

    discard = AsyncMock()
    monkeypatch.setattr(database, "AsyncSessionLocal", same_session)
    monkeypatch.setattr(analysis_service, "discard_queued_task", discard)

    await analysis_queue._cleanup_failed_alert_dispatch(stable_task_id, test_user)

    assert (
        await db.execute(select(AnalysisResult).where(AnalysisResult.task_id == stable_task_id))
    ).scalar_one_or_none() is None
    discard.assert_awaited_once_with(stable_task_id, test_user.id)
