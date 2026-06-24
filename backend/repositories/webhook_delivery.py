from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.webhook_delivery import WebhookDelivery


async def list_webhook_deliveries(db: AsyncSession, user_id: int, limit: int = 20) -> list[WebhookDelivery]:
    q = (
        select(WebhookDelivery)
        .where(WebhookDelivery.user_id == user_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars().all())
