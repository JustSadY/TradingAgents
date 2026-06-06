from __future__ import annotations
import asyncio
import logging
from typing import Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import AsyncSessionLocal
from backend.repositories.analysis import get_analysis_by_id
from backend.services.notification_service import notify_analysis_complete
from backend.services.annotation_service import extract_chart_annotations

_logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task] = set()
_ANALYSIS_BACKGROUND_TASKS: dict[str, set[asyncio.Task]] = {}

def track_background_task(coro: Awaitable[None], task_id: str | None = None):
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    if task_id:
        tasks = _ANALYSIS_BACKGROUND_TASKS.setdefault(task_id, set())
        tasks.add(task)

    def _cleanup(done_task: asyncio.Task) -> None:
        _BACKGROUND_TASKS.discard(done_task)
        if task_id and task_id in _ANALYSIS_BACKGROUND_TASKS:
            scoped = _ANALYSIS_BACKGROUND_TASKS[task_id]
            scoped.discard(done_task)
            if not scoped:
                _ANALYSIS_BACKGROUND_TASKS.pop(task_id, None)

    task.add_done_callback(_cleanup)
    return task


async def await_analysis_background_tasks(task_id: str) -> None:
    pending = list(_ANALYSIS_BACKGROUND_TASKS.get(task_id, set()))
    if not pending:
        return
    await asyncio.gather(*pending, return_exceptions=True)


async def send_analysis_webhook(ticker, trade_date, signal, final_decision, settings):
    try:
        await notify_analysis_complete(ticker, signal, trade_date, final_decision, settings)
    except Exception as exc:
        _logger.debug("Webhook notify failed (non-fatal): %s", exc)


async def extract_and_save_annotations(
    analysis_id: int,
    market_report: str,
    final_decision: str,
    quick_llm,
    custom_indicators: list = None,
    visual_annotations: list = None,
    output_language: str = "English",
) -> None:
    try:
        annotations = await extract_chart_annotations(market_report, final_decision, quick_llm, output_language=output_language)
        if not annotations:
            annotations = {}
        if custom_indicators:
            annotations["custom_indicators"] = custom_indicators
        if visual_annotations:
            annotations["annotations"] = visual_annotations
        if not annotations:
            return
        async with AsyncSessionLocal() as s:
            from backend.repositories.analysis import get_analysis_by_id as _repo_get
            row = await _repo_get(s, analysis_id)
            if row:
                row.chart_annotations = annotations
                await s.commit()
    except Exception as exc:
        _logger.debug("Annotation save failed (non-fatal): %s", exc)
