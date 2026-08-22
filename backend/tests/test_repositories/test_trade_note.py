from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Portfolio
from backend.repositories.trade_note import get_note, set_debrief, upsert_note


class TestTradeNoteRepository:
    async def _create_orders(self, db: AsyncSession, user_id: int, count: int = 1) -> list[Order]:
        portfolio = Portfolio(
            user_id=user_id,
            mode="simulation",
            broker="paper",
            initial_capital=Decimal("100000"),
            current_balance=Decimal("100000"),
            cash_available=Decimal("100000"),
        )
        db.add(portfolio)
        await db.flush()

        orders = [
            Order(
                portfolio_id=portfolio.id,
                broker="paper",
                ticker=f"TEST{index}",
                action="BUY",
                quantity_requested=Decimal("1"),
                quantity_filled=Decimal("1"),
                status="FILLED",
                price_per_share=Decimal("100"),
                total_value=Decimal("100"),
            )
            for index in range(count)
        ]
        db.add_all(orders)
        await db.flush()
        return orders

    async def test_upsert_note_create(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        note = await upsert_note(db, order_id=order.id, user_id=test_user.id, note="My trade note")
        assert note.id is not None
        assert note.note == "My trade note"
        assert note.order_id == order.id
        assert note.user_id == test_user.id

    async def test_upsert_note_update(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        note = await upsert_note(db, order_id=order.id, user_id=test_user.id, note="Original note")
        note_id = note.id

        updated = await upsert_note(db, order_id=order.id, user_id=test_user.id, note="Updated note")
        assert updated.id == note_id
        assert updated.note == "Updated note"

    async def test_get_note(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        await upsert_note(db, order_id=order.id, user_id=test_user.id, note="My note")

        found = await get_note(db, order_id=order.id, user_id=test_user.id)
        assert found is not None
        assert found.note == "My note"

    async def test_get_note_scoped_to_user(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        await upsert_note(db, order_id=order.id, user_id=test_user.id, note="User's note")

        other_note = await get_note(db, order_id=order.id, user_id=99999)
        assert other_note is None

    async def test_get_note_nonexistent(self, db: AsyncSession, test_user):
        found = await get_note(db, order_id=999, user_id=test_user.id)
        assert found is None

    async def test_set_debrief(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        await upsert_note(db, order_id=order.id, user_id=test_user.id, note="Note")
        await set_debrief(db, order_id=order.id, user_id=test_user.id, debrief="AI analysis of trade")

        note = await get_note(db, order_id=order.id, user_id=test_user.id)
        assert note.ai_debrief == "AI analysis of trade"

    async def test_set_debrief_creates_note_if_not_exists(self, db: AsyncSession, test_user):
        order = (await self._create_orders(db, test_user.id))[0]
        await set_debrief(db, order_id=order.id, user_id=test_user.id, debrief="AI debrief without prior note")

        note = await get_note(db, order_id=order.id, user_id=test_user.id)
        assert note is not None
        assert note.ai_debrief == "AI debrief without prior note"
        assert note.note == ""

