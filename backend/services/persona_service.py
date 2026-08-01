from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.persona import UserPersona
from backend.repositories.persona import (
    create_user_persona,
    delete_user_persona,
    get_user_persona_by_key,
    list_user_personas,
    update_user_persona,
)

async def get_user_personas(db: AsyncSession, user_id: int) -> list[UserPersona]:
    return await list_user_personas(db, user_id)

async def check_duplicate_persona(db: AsyncSession, user_id: int, key: str) -> bool:
    persona = await get_user_persona_by_key(db, user_id, key)
    return persona is not None

async def get_persona(db: AsyncSession, user_id: int, key: str) -> UserPersona | None:
    return await get_user_persona_by_key(db, user_id, key)

async def add_persona(
    db: AsyncSession,
    user_id: int,
    key: str,
    label: str,
    description: str,
    instructions: str,
) -> UserPersona:
    persona = await create_user_persona(db, user_id, key, label, description, instructions)
    await db.commit()
    return persona

async def edit_persona(
    db: AsyncSession,
    persona: UserPersona,
    label: str,
    description: str,
    instructions: str,
) -> UserPersona:
    updated = await update_user_persona(db, persona, label, description, instructions)
    await db.commit()
    return updated

async def remove_persona(db: AsyncSession, persona: UserPersona) -> None:
    await delete_user_persona(db, persona)
    await db.commit()
