"""Lightweight facade for the decomposed analysis subsystem.

Responsibilities have been moved to:
- .orchestrator: High-level task flow (run_analysis)
- .persistence: Incremental and final DB updates
- .emitter: Real-time event broadcasting (WS)
- .config_builder: Config dictionary assembly
- .tasks: Background extraction and notification tasks
- .portfolio_orchestrator: Multi-ticker synthesis
"""
from __future__ import annotations
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AsyncSessionLocal
from backend.models.settings import AppSettings
from backend.services.trading_orchestrator import place_signal_order

# Sub-module imports
from .analysis.orchestrator import run_individual_analysis
from .analysis.portfolio_orchestrator import run_portfolio_analysis
from .analysis.emitter import AnalysisEmitter
from .analysis.tasks import (
    _BACKGROUND_TASKS, _ANALYSIS_BACKGROUND_TASKS,
    track_background_task, await_analysis_background_tasks,
    send_analysis_webhook, extract_and_save_annotations
)

_logger = logging.getLogger(__name__)

# Maintain local references for backward compatibility with existing imports
_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_TASK_REGISTRY: dict[str, dict] = {} # Re-used by get_active_tasks_for_user


async def cancel_analysis(task_id: str) -> bool:
    task = _RUNNING_TASKS.pop(task_id, None)
    _TASK_REGISTRY.pop(task_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def get_active_tasks_for_user(user_id: int | None) -> list[dict]:
    """Returns a list of active tasks for the given user."""
    return [
        {"task_id": tid, **meta}
        for tid, meta in _TASK_REGISTRY.items()
        if meta.get("user_id") == user_id
    ]


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    task_id: str | None = None,
    user=None,
):
    """Facade for individual analysis orchestration."""
    import uuid
    import time
    if task_id is None:
        task_id = str(uuid.uuid4())
    
    current = asyncio.current_task()
    if current:
        _RUNNING_TASKS[task_id] = current
        _TASK_REGISTRY[task_id] = {
            "ticker": ticker,
            "trade_date": trade_date,
            "asset_type": asset_type,
            "user_id": user.id if user else None,
            "started_at": time.time(),
            "status": "running"
        }

    emitter = AnalysisEmitter(task_id)
    try:
        return await run_individual_analysis(
            ticker, trade_date, asset_type, settings, db, emitter, triggered_by, user
        )
    finally:
        _RUNNING_TASKS.pop(task_id, None)
        _TASK_REGISTRY.pop(task_id, None)
        await emitter.close()


async def run_analysis_task(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    task_id: str,
    user=None,
) -> None:
    """Background entrypoint for a single manual analysis run."""
    async with AsyncSessionLocal() as db:
        try:
            _, row = await run_analysis(
                ticker, trade_date, asset_type, settings, db, "manual",
                task_id=task_id, user=user,
            )
            # Signal-based paper trading
            try:
                await place_signal_order(db, ticker=ticker, row=row, settings=settings, user=user)
                await db.commit()
            except Exception as exc:
                _logger.warning("Order execution skipped for %s: %s", ticker, exc)
                await db.rollback()
        except Exception as exc:
            _logger.error("Background analysis failed: %s", exc, exc_info=True)
            await db.rollback()


async def run_portfolio_task(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    user=None,
) -> None:
    """Background entrypoint for a multi-ticker portfolio analysis run."""
    async with AsyncSessionLocal() as db:
        try:
            await run_portfolio_analysis(
                tickers, trade_date, asset_type, settings, db, "manual", user=user,
            )
            await db.commit()
        except Exception as exc:
            _logger.error("Portfolio analysis failed: %s", exc, exc_info=True)
            await db.rollback()
