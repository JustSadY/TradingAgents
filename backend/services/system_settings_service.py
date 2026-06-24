from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.system_settings import SystemSettings
from backend.repositories import system_settings as repo


async def get_or_create_system_settings(db: AsyncSession) -> SystemSettings:
    ss = await repo.get_system_settings_by_id(db, 1)
    if ss is None:
        ss = await repo.create_system_settings(db, 1)
    return ss


async def update_system_settings(db: AsyncSession, fields: dict) -> SystemSettings:
    ss = await get_or_create_system_settings(db)
    updated_fields = {**fields, "updated_at": datetime.now(UTC)}
    updated_ss = await repo.update_system_settings_fields(db, ss, **updated_fields)
    return updated_ss
