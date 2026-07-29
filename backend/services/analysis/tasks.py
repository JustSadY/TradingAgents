from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable

from backend.core.database import AsyncSessionLocal
from backend.services.annotation_service import extract_chart_annotations
from backend.services.notification_service import notify_analysis_complete, notify_signal_flip

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


async def send_signal_flip_webhook(ticker, prev_signal, new_signal, settings):
    try:
        await notify_signal_flip(ticker, prev_signal, new_signal, settings)
    except Exception as exc:
        _logger.debug("Signal-flip notify failed (non-fatal): %s", exc)


async def extract_and_save_annotations(
    analysis_id: int,
    market_report: str,
    final_decision: str,
    quick_llm,
    custom_indicators: list = None,
    visual_annotations: list = None,
    support_levels: list = None,
    resistance_levels: list = None,
    output_language: str = "English",
) -> None:
    try:
        annotations = await extract_chart_annotations(
            market_report, final_decision, quick_llm, output_language=output_language
        )
        if not annotations:
            annotations = {}
        if custom_indicators:
            annotations["custom_indicators"] = custom_indicators
        if visual_annotations:
            annotations["annotations"] = visual_annotations
        if support_levels:
            existing_sups = annotations.setdefault("support_levels", [])
            for s in support_levels:
                if s not in existing_sups:
                    existing_sups.append(s)
        if resistance_levels:
            existing_res = annotations.setdefault("resistance_levels", [])
            for r in resistance_levels:
                if r not in existing_res:
                    existing_res.append(r)
        if not annotations:
            return
        async with AsyncSessionLocal() as s:
            from backend.repositories.analysis import get_analysis_by_id as _repo_get

            row = await _repo_get(s, analysis_id)
            if row:
                # Merge rather than overwrite: finalize_result already stored the
                # structured trader_proposal (entry/stop/target/confidence) that
                # position sizing reads. A blind assignment here dropped it,
                # leaving sizing to fall back to fragile text parsing.
                existing = row.chart_annotations if isinstance(row.chart_annotations, dict) else {}
                row.chart_annotations = {**existing, **annotations}

                # Auto-generate support/resistance alerts if user_id is set
                if row.user_id:
                    from decimal import Decimal

                    from backend.services.alert_creation_service import create_alert_with_guardrails

                    for sup in annotations.get("support_levels") or []:
                        price_dec = Decimal(str(round(float(sup), 2)))
                        await create_alert_with_guardrails(
                            s,
                            user_id=row.user_id,
                            ticker=row.ticker,
                            condition="below",
                            target_price=float(price_dec),
                            auto_analyze=True,
                            alert_type="support",
                            creation_source="analysis",
                            creation_run_id=str(analysis_id),
                            skip_if_limited=True,
                        )

                    for res in annotations.get("resistance_levels") or []:
                        price_dec = Decimal(str(round(float(res), 2)))
                        await create_alert_with_guardrails(
                            s,
                            user_id=row.user_id,
                            ticker=row.ticker,
                            condition="above",
                            target_price=float(price_dec),
                            auto_analyze=True,
                            alert_type="resistance",
                            creation_source="analysis",
                            creation_run_id=str(analysis_id),
                            skip_if_limited=True,
                        )
                await s.commit()
    except Exception as exc:
        _logger.debug("Annotation save failed (non-fatal): %s", exc)
