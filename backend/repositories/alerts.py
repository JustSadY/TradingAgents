from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.repositories.common import scope_to_user


async def list_alerts(db: AsyncSession, user=None) -> list[PriceAlert]:
    q = select(PriceAlert).order_by(PriceAlert.created_at.desc())
    q = scope_to_user(q, PriceAlert, user)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_enabled_alerts(db: AsyncSession) -> list[PriceAlert]:
    result = await db.execute(
        select(PriceAlert).where(PriceAlert.enabled.is_(True), PriceAlert.triggered_at.is_(None))
    )
    return list(result.scalars().all())


async def get_alert_by_id(db: AsyncSession, alert_id: int, user=None) -> PriceAlert | None:
    q = select(PriceAlert).where(PriceAlert.id == alert_id)
    q = scope_to_user(q, PriceAlert, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def insert_alert(
    db: AsyncSession,
    user_id: int,
    ticker: str,
    condition: str,
    target_price: float,
    auto_analyze: bool,
    alert_type: str = "price",
    creation_source: str = "manual",
    creation_run_id: str | None = None,
) -> PriceAlert:
    """Persist an already-authorized alert.

    User-facing callers must use ``alert_creation_service`` first; keeping
    count/cooldown policy out of this primitive prevents repository helpers
    from silently starting transactions or owning API-facing error semantics.
    """
    alert = PriceAlert(
        ticker=ticker.upper(),
        alert_type=alert_type,
        condition=condition,
        target_price=target_price,
        auto_analyze=auto_analyze,
        user_id=user_id,
        creation_source=creation_source,
        creation_run_id=creation_run_id,
    )
    db.add(alert)
    await db.flush()
    return alert


async def apply_alert_changes(
    db: AsyncSession,
    alert: PriceAlert,
    changes: dict[str, Any],
) -> PriceAlert:
    """Persist already-validated alert field changes."""
    for field, value in changes.items():
        setattr(alert, field, value)
    await db.flush()
    return alert


async def delete_alert_row(db: AsyncSession, alert: PriceAlert) -> None:
    """Delete an already-authorized alert row."""
    await db.delete(alert)
    await db.flush()
