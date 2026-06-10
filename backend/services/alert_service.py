import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.models.alert import PriceAlert
from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.services.analysis_service import run_analysis
from backend.services.market_data_service import get_live_prices_batch
from backend.services.notification_service import notify_alert_triggered
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# Concurrency limits
_RECOVERY_SEMAPHORE = asyncio.Semaphore(3)
_ALERT_SEMAPHORE = asyncio.Semaphore(5)


async def check_price_alerts() -> None:
    async with AsyncSessionLocal() as db:
        from backend.repositories.alerts import get_enabled_alerts

        alerts = await get_enabled_alerts(db)
        if not alerts:
            return

        from backend.repositories.analysis import get_system_settings

        settings = await get_system_settings(db)

        prices = await get_live_prices_batch([a.ticker for a in alerts])

        for alert in alerts:
            price = prices.get(alert.ticker)
            if price is None:
                continue

            hit = (alert.condition == "above" and price >= alert.target_price) or (
                alert.condition == "below" and price <= alert.target_price
            )
            if not hit:
                continue

            alert.triggered_at = datetime.now(UTC)
            _logger.info(
                "Alert triggered: %s %s $%.2f (current: $%.2f)",
                alert.ticker,
                alert.condition,
                alert.target_price,
                price,
            )

            if settings:
                # Resolve the alert owner's AppSettings (holds the webhook config) so the
                # notification respects that user's delivery preferences.
                user = await db.get(User, alert.user_id)
                user_settings = await get_or_create_settings(db, user)
                await notify_alert_triggered(
                    alert.ticker,
                    alert.condition,
                    alert.target_price,
                    user_settings,
                    alert_type=getattr(alert, "alert_type", "price")
                )

            if alert.auto_analyze:
                today = datetime.now(UTC).strftime("%Y-%m-%d")
                task = asyncio.create_task(_throttled_analyze(alert.ticker, today, alert.user_id, _ALERT_SEMAPHORE))
                _BACKGROUND_TASKS.add(task)
                task.add_done_callback(_BACKGROUND_TASKS.discard)
        await db.commit()


async def _throttled_analyze(ticker: str, trade_date: str, user_id: int, semaphore: asyncio.Semaphore) -> None:
    """Acquire *semaphore* before running ``_auto_analyze`` to cap concurrency."""
    async with semaphore:
        await _auto_analyze(ticker, trade_date, user_id)


async def _auto_analyze(ticker: str, trade_date: str, user_id: int) -> None:
    try:
        async with AsyncSessionLocal() as new_db:
            result = await new_db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return
            settings = await get_or_create_settings(new_db, user)
            task_id = str(uuid.uuid4())
            await run_analysis(
                ticker, trade_date, "stock", settings, new_db, triggered_by="alert", task_id=task_id, user=user
            )
            await new_db.commit()
    except Exception as exc:
        _logger.error("Auto-analyze from alert failed %s: %s", ticker, exc)


async def check_and_recover_lost_alerts() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert)
            .where(PriceAlert.enabled == True)
            .where(PriceAlert.triggered_at.isnot(None))
            .where(PriceAlert.auto_analyze == True)
        )
        triggered_alerts = result.scalars().all()
        missing: list[tuple[str, str, int]] = []
        for alert in triggered_alerts:
            trigger_date = alert.triggered_at.strftime("%Y-%m-%d")
            res_analysis = await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.ticker == alert.ticker)
                .where(AnalysisResult.trade_date == trigger_date)
                .where(AnalysisResult.user_id == alert.user_id)
                .where(AnalysisResult.triggered_by == "alert")
            )
            analysis = res_analysis.scalar_one_or_none()
            if not analysis:
                _logger.warning(
                    "Recovering lost alert analysis task for %s (triggered at %s)",
                    alert.ticker,
                    trigger_date,
                )
                missing.append((alert.ticker, trigger_date, alert.user_id))

        if not missing:
            return

        batch_size = 3
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            await asyncio.gather(
                *[
                    _throttled_analyze(ticker, trade_date, user_id, _RECOVERY_SEMAPHORE)
                    for ticker, trade_date, user_id in batch
                ],
                return_exceptions=True,
            )
            if i + batch_size < len(missing):
                await asyncio.sleep(0.5)
