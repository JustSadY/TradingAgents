from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories.alerts import (
    create_alert,
    get_alert_by_id,
    get_enabled_alerts,
    list_alerts,
)


class TestAlertRepository:
    async def test_create_alert(self, db: AsyncSession, test_user: User):
        alert = await create_alert(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            condition="above",
            target_price=200.0,
            auto_analyze=True,
        )
        assert alert.id is not None
        assert alert.ticker == "AAPL"
        assert alert.condition == "above"
        assert alert.target_price == 200.0
        assert alert.enabled is True
        assert alert.triggered_at is None

    async def test_list_alerts(self, db: AsyncSession, test_user: User):
        await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)
        await create_alert(db, user_id=test_user.id, ticker="GOOGL", condition="below", target_price=150.0, auto_analyze=True)

        alerts = await list_alerts(db, user=test_user)
        assert len(alerts) == 2

    async def test_list_alerts_scoped(self, db: AsyncSession, test_user: User, admin_user: User):
        await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)

        user_alerts = await list_alerts(db, user=test_user)
        assert len(user_alerts) == 1

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        other_alerts = await list_alerts(db, user=other_user)
        assert len(other_alerts) == 0

    async def test_get_alert_by_id(self, db: AsyncSession, test_user: User):
        alert = await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)

        found = await get_alert_by_id(db, alert.id, user=test_user)
        assert found is not None
        assert found.id == alert.id

    async def test_get_alert_by_id_scoped(self, db: AsyncSession, test_user: User):
        alert = await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        found = await get_alert_by_id(db, alert.id, user=other_user)
        assert found is None

    async def test_get_alert_by_id_admin(self, db: AsyncSession, test_user: User, admin_user: User):
        alert = await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)

        found = await get_alert_by_id(db, alert.id, user=admin_user)
        assert found is not None

    async def test_get_enabled_alerts(self, db: AsyncSession, test_user: User):
        a1 = await create_alert(db, user_id=test_user.id, ticker="AAPL", condition="above", target_price=200.0, auto_analyze=False)
        a2 = await create_alert(db, user_id=test_user.id, ticker="GOOGL", condition="below", target_price=150.0, auto_analyze=True)

        a2.enabled = False
        await db.flush()

        enabled = await get_enabled_alerts(db)
        assert len(enabled) == 1
        assert enabled[0].id == a1.id
