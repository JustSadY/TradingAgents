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
    result = await db.execute(select(PriceAlert).where(PriceAlert.enabled == True, PriceAlert.triggered_at.is_(None)))
    return list(result.scalars().all())


async def get_alert_by_id(db: AsyncSession, alert_id: int, user=None) -> PriceAlert | None:
    q = select(PriceAlert).where(PriceAlert.id == alert_id)
    q = scope_to_user(q, PriceAlert, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def create_alert(
    db: AsyncSession, user_id: int, ticker: str, condition: str, target_price: float, auto_analyze: bool, alert_type: str = "price"
) -> PriceAlert:
    alert = PriceAlert(
        ticker=ticker.upper(),
        alert_type=alert_type,
        condition=condition,
        target_price=target_price,
        auto_analyze=auto_analyze,
        user_id=user_id,
    )
    db.add(alert)
    await db.flush()
    return alert
