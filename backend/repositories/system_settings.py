from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.system_settings import SystemSettings


async def get_system_settings_by_id(db: AsyncSession, ss_id: int = 1) -> SystemSettings | None:
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == ss_id))
    return result.scalar_one_or_none()


async def get_system_settings(db: AsyncSession) -> SystemSettings | None:
    """The singleton system settings row (id=1) — used by the analysis/trading
    engine to read the active broker/trading-mode/data-vendor config."""
    return await get_system_settings_by_id(db)


async def create_system_settings(db: AsyncSession, ss_id: int = 1) -> SystemSettings:
    ss = SystemSettings(id=ss_id)
    db.add(ss)
    await db.flush()
    return ss


async def update_system_settings_fields(db: AsyncSession, ss: SystemSettings, **fields) -> SystemSettings:
    for field, value in fields.items():
        setattr(ss, field, value)
    await db.flush()
    return ss
