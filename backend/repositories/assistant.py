from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.assistant import AssistantMessage


async def get_messages(db: AsyncSession, user_id: int, limit: int = 30) -> list[AssistantMessage]:
    result = await db.execute(
        select(AssistantMessage)
        .where(AssistantMessage.user_id == user_id)
        .order_by(AssistantMessage.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def add_message(db: AsyncSession, user_id: int, role: str, content: str) -> AssistantMessage:
    msg = AssistantMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg


async def clear_messages(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(AssistantMessage).where(AssistantMessage.user_id == user_id))
