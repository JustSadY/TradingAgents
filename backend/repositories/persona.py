from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.persona import UserPersona


async def list_user_personas(db: AsyncSession, user_id: int) -> list[UserPersona]:
    result = await db.execute(select(UserPersona).where(UserPersona.user_id == user_id))
    return list(result.scalars().all())


async def get_user_persona_by_key(db: AsyncSession, user_id: int, key: str) -> UserPersona | None:
    result = await db.execute(
        select(UserPersona).where(
            UserPersona.user_id == user_id,
            UserPersona.key == key,
        )
    )
    return result.scalar_one_or_none()


async def create_user_persona(
    db: AsyncSession,
    user_id: int,
    key: str,
    label: str,
    description: str,
    instructions: str,
) -> UserPersona:
    persona = UserPersona(
        user_id=user_id,
        key=key,
        label=label,
        description=description,
        instructions=instructions,
    )
    db.add(persona)
    await db.flush()
    return persona


async def update_user_persona(
    db: AsyncSession,
    persona: UserPersona,
    label: str,
    description: str,
    instructions: str,
) -> UserPersona:
    persona.label = label
    persona.description = description
    persona.instructions = instructions
    await db.flush()
    return persona


async def delete_user_persona(db: AsyncSession, persona: UserPersona) -> None:
    await db.delete(persona)
    await db.flush()
