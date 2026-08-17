from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.models.settings import AppSettings


async def lock_user_alert_settings(db: AsyncSession, user_id: int) -> AppSettings | None:
    """Lock the single settings row used to serialize alert creation policy."""
    statement = select(AppSettings).where(AppSettings.user_id == user_id).with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def count_active_alerts(
    db: AsyncSession,
    user_id: int,
    *,
    exclude_alert_id: int | None = None,
) -> int:
    statement = select(func.count(PriceAlert.id)).where(
        PriceAlert.user_id == user_id,
        PriceAlert.enabled.is_(True),
        PriceAlert.triggered_at.is_(None),
    )
    if exclude_alert_id is not None:
        statement = statement.where(PriceAlert.id != exclude_alert_id)
    return int((await db.execute(statement)).scalar_one())


async def count_analysis_alerts_for_run(db: AsyncSession, user_id: int, run_id: str) -> int:
    result = await db.execute(
        select(func.count(PriceAlert.id)).where(
            PriceAlert.user_id == user_id,
            PriceAlert.creation_source == "analysis",
            PriceAlert.creation_run_id == run_id,
        )
    )
    return int(result.scalar_one())


async def recent_equivalent_analysis_alert_exists(
    db: AsyncSession,
    *,
    user_id: int,
    ticker: str,
    condition: str,
    alert_type: str,
    exclude_run_id: str,
    created_at_or_after: datetime,
) -> bool:
    result = await db.execute(
        select(PriceAlert.id)
        .where(
            PriceAlert.user_id == user_id,
            PriceAlert.creation_source == "analysis",
            PriceAlert.ticker == ticker,
            PriceAlert.condition == condition,
            PriceAlert.alert_type == alert_type,
            PriceAlert.creation_run_id != exclude_run_id,
            PriceAlert.created_at >= created_at_or_after,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def active_exact_alert_exists(
    db: AsyncSession,
    *,
    user_id: int,
    ticker: str,
    condition: str,
    target_price: Decimal,
    alert_type: str,
) -> bool:
    result = await db.execute(
        select(PriceAlert.id)
        .where(
            PriceAlert.user_id == user_id,
            PriceAlert.ticker == ticker,
            PriceAlert.condition == condition,
            PriceAlert.target_price == target_price,
            PriceAlert.alert_type == alert_type,
            PriceAlert.enabled.is_(True),
            PriceAlert.triggered_at.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def rearm_alert_row(db: AsyncSession, alert: PriceAlert) -> PriceAlert:
    alert.enabled = True
    alert.triggered_at = None
    await db.flush()
    return alert
