from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.webhook_delivery import WebhookDelivery
from backend.repositories.webhook_delivery import list_webhook_deliveries


class TestWebhookDeliveryRepository:
    async def _create_delivery(
        self, db: AsyncSession, user_id: int, event: str = "analysis_complete", success: bool = True, **overrides
    ) -> WebhookDelivery:
        fields = {
            "user_id": user_id,
            "event": event,
            "url": "https://hooks.example.com/test",
            "success": success,
            "status_code": 200,
        }
        fields.update(overrides)
        delivery = WebhookDelivery(**fields)
        db.add(delivery)
        await db.flush()
        return delivery

    async def test_list_webhook_deliveries(self, db: AsyncSession, test_user):
        await self._create_delivery(db, test_user.id, event="analysis_complete")
        await self._create_delivery(db, test_user.id, event="order_filled")

        deliveries = await list_webhook_deliveries(db, test_user.id)
        assert len(deliveries) == 2

    async def test_list_webhook_deliveries_scoped(self, db: AsyncSession, test_user):
        await self._create_delivery(db, test_user.id, event="analysis_complete")

        deliveries = await list_webhook_deliveries(db, test_user.id)
        assert len(deliveries) == 1

        other_deliveries = await list_webhook_deliveries(db, 99999)
        assert len(other_deliveries) == 0

    async def test_list_webhook_deliveries_limit(self, db: AsyncSession, test_user):
        for i in range(5):
            await self._create_delivery(db, test_user.id, event=f"event_{i}")

        deliveries = await list_webhook_deliveries(db, test_user.id, limit=3)
        assert len(deliveries) == 3

    async def test_list_webhook_deliveries_ordered_by_newest(self, db: AsyncSession, test_user):
        d1 = await self._create_delivery(db, test_user.id)
        d2 = await self._create_delivery(db, test_user.id)

        deliveries = await list_webhook_deliveries(db, test_user.id)
        assert len(deliveries) == 2
        assert deliveries[0].id == d2.id
        assert deliveries[1].id == d1.id

    async def test_list_webhook_deliveries_tracks_failure(self, db: AsyncSession, test_user):
        d = await self._create_delivery(db, test_user.id, success=False, status_code=500, error="Timeout")
        assert d.success is False
        assert d.error == "Timeout"
        assert d.status_code == 500

    async def test_list_webhook_deliveries_empty(self, db: AsyncSession, test_user):
        deliveries = await list_webhook_deliveries(db, test_user.id)
        assert len(deliveries) == 0
