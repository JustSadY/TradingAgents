from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.trade_note import clear_debrief, get_note, get_notes_for_orders, set_debrief, upsert_note


class TestTradeNoteRepository:
    async def test_upsert_note_create(self, db: AsyncSession, test_user):
        note = await upsert_note(db, order_id=1, user_id=test_user.id, note="My trade note")
        assert note.id is not None
        assert note.note == "My trade note"
        assert note.order_id == 1
        assert note.user_id == test_user.id

    async def test_upsert_note_update(self, db: AsyncSession, test_user):
        note = await upsert_note(db, order_id=1, user_id=test_user.id, note="Original note")
        note_id = note.id

        updated = await upsert_note(db, order_id=1, user_id=test_user.id, note="Updated note")
        assert updated.id == note_id
        assert updated.note == "Updated note"

    async def test_get_note(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="My note")

        found = await get_note(db, order_id=1, user_id=test_user.id)
        assert found is not None
        assert found.note == "My note"

    async def test_get_note_scoped_to_user(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="User's note")

        other_note = await get_note(db, order_id=1, user_id=99999)
        assert other_note is None

    async def test_get_note_nonexistent(self, db: AsyncSession, test_user):
        found = await get_note(db, order_id=999, user_id=test_user.id)
        assert found is None

    async def test_set_debrief(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="Note")
        await set_debrief(db, order_id=1, user_id=test_user.id, debrief="AI analysis of trade")

        note = await get_note(db, order_id=1, user_id=test_user.id)
        assert note.ai_debrief == "AI analysis of trade"

    async def test_set_debrief_creates_note_if_not_exists(self, db: AsyncSession, test_user):
        await set_debrief(db, order_id=1, user_id=test_user.id, debrief="AI debrief without prior note")

        note = await get_note(db, order_id=1, user_id=test_user.id)
        assert note is not None
        assert note.ai_debrief == "AI debrief without prior note"
        assert note.note == ""

    async def test_clear_debrief(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="Note")
        await set_debrief(db, order_id=1, user_id=test_user.id, debrief="Some debrief")

        await clear_debrief(db, order_id=1, user_id=test_user.id)
        note = await get_note(db, order_id=1, user_id=test_user.id)
        assert note.ai_debrief is None

    async def test_get_notes_for_orders(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="Order 1 note")
        await upsert_note(db, order_id=2, user_id=test_user.id, note="Order 2 note")

        notes_map = await get_notes_for_orders(db, [1, 2], user_id=test_user.id)
        assert len(notes_map) == 2
        assert notes_map[1].note == "Order 1 note"
        assert notes_map[2].note == "Order 2 note"

    async def test_get_notes_for_orders_partial(self, db: AsyncSession, test_user):
        await upsert_note(db, order_id=1, user_id=test_user.id, note="Only order 1")

        notes_map = await get_notes_for_orders(db, [1, 999], user_id=test_user.id)
        assert len(notes_map) == 1
        assert notes_map[1].note == "Only order 1"

    async def test_get_notes_for_orders_empty_list(self, db: AsyncSession, test_user):
        notes_map = await get_notes_for_orders(db, [], user_id=test_user.id)
        assert notes_map == {}