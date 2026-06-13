from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.trade_note import TradeNote


async def get_note(db: AsyncSession, order_id: int, user_id: int) -> TradeNote | None:
    result = await db.execute(
        select(TradeNote)
        .where(TradeNote.order_id == order_id)
        .where(TradeNote.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def upsert_note(db: AsyncSession, order_id: int, user_id: int, note: str) -> TradeNote:
    existing = await get_note(db, order_id, user_id)
    if existing:
        existing.note = note
        existing.updated_at = datetime.now(UTC)
        await db.flush()
        return existing
    trade_note = TradeNote(order_id=order_id, user_id=user_id, note=note)
    db.add(trade_note)
    await db.flush()
    return trade_note


async def clear_debrief(db: AsyncSession, order_id: int, user_id: int) -> None:
    existing = await get_note(db, order_id, user_id)
    if existing:
        existing.ai_debrief = None
        await db.flush()


async def set_debrief(db: AsyncSession, order_id: int, user_id: int, debrief: str) -> None:
    existing = await get_note(db, order_id, user_id)
    if existing:
        existing.ai_debrief = debrief
        existing.updated_at = datetime.now(UTC)
        await db.flush()
    else:
        trade_note = TradeNote(order_id=order_id, user_id=user_id, note="", ai_debrief=debrief)
        db.add(trade_note)
        await db.flush()


async def get_notes_for_orders(db: AsyncSession, order_ids: list[int], user_id: int) -> dict[int, TradeNote]:
    if not order_ids:
        return {}
    result = await db.execute(
        select(TradeNote)
        .where(TradeNote.order_id.in_(order_ids))
        .where(TradeNote.user_id == user_id)
    )
    notes = result.scalars().all()
    return {note.order_id: note for note in notes}
