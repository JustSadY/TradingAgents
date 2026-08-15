from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.assistant import AssistantMessage


async def get_messages(db: AsyncSession, user_id: int, limit: int = 30) -> list[AssistantMessage]:
    """Return only one user's private assistant conversation.

    Assistant history is never an administrator-wide resource.  In
    particular, using the generic ``scope_to_user`` helper here would remove
    the owner filter for admins and send other users' messages to the LLM.
    """
    q = (
        select(AssistantMessage)
        .where(AssistantMessage.user_id == user_id)
        .order_by(AssistantMessage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(reversed(result.scalars().all()))

async def add_message(db: AsyncSession, user_id: int, role: str, content: str) -> AssistantMessage:
    msg = AssistantMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg

async def clear_messages(db: AsyncSession, user_id: int) -> None:
    """Delete only one user's assistant history, including for admins."""
    q = delete(AssistantMessage).where(AssistantMessage.user_id == user_id)
    await db.execute(q)
