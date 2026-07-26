from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.assistant import AssistantMessage
from backend.repositories.common import scope_to_user


async def get_messages(db: AsyncSession, user, limit: int = 30) -> list[AssistantMessage]:
    q = select(AssistantMessage).order_by(AssistantMessage.created_at.desc()).limit(limit)
    q = scope_to_user(q, AssistantMessage, user)
    result = await db.execute(q)
    return list(reversed(result.scalars().all()))


async def add_message(db: AsyncSession, user, role: str, content: str) -> AssistantMessage:
    user_id = user.id if user else None
    msg = AssistantMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg


async def clear_messages(db: AsyncSession, user) -> None:
    q = delete(AssistantMessage)
    if user is not None and not getattr(user, "is_admin", False):
        q = q.where(AssistantMessage.user_id == user.id)
    await db.execute(q)
