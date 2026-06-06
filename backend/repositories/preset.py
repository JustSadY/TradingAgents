from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.preset import ConfigPreset
from backend.repositories.common import scope_to_user

async def list_presets(db: AsyncSession, user=None) -> list[ConfigPreset]:
    q = select(ConfigPreset).order_by(ConfigPreset.created_at.desc())
    q = scope_to_user(q, ConfigPreset, user)
    result = await db.execute(q)
    return list(result.scalars().all())

async def get_preset_by_id(db: AsyncSession, preset_id: int, user=None) -> ConfigPreset | None:
    q = select(ConfigPreset).where(ConfigPreset.id == preset_id)
    q = scope_to_user(q, ConfigPreset, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()

async def get_preset_by_name(db: AsyncSession, name: str, user_id: int) -> ConfigPreset | None:
    q = select(ConfigPreset).where(ConfigPreset.name == name, ConfigPreset.user_id == user_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()

async def create_preset(db: AsyncSession, user_id: int, name: str, description: str, settings_json: str) -> ConfigPreset:
    preset = ConfigPreset(
        name=name,
        description=description,
        settings_json=settings_json,
        user_id=user_id,
    )
    db.add(preset)
    await db.flush()
    return preset
