from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings


def _settings_owner_clause(user_id: int | None):
    return AppSettings.user_id == user_id if user_id is not None else AppSettings.user_id.is_(None)


async def get_app_settings(db: AsyncSession, user_id: int | None) -> AppSettings | None:
    result = await db.execute(select(AppSettings).where(_settings_owner_clause(user_id)).limit(1))
    return result.scalar_one_or_none()


async def get_app_settings_map(db: AsyncSession, user_ids: set[int]) -> dict[int, AppSettings]:
    """Load settings for multiple tenant owners in one query."""
    if not user_ids:
        return {}
    result = await db.execute(select(AppSettings).where(AppSettings.user_id.in_(user_ids)))
    return {int(row.user_id): row for row in result.scalars().all() if row.user_id is not None}


async def get_or_create_app_settings(db: AsyncSession, user_id: int | None) -> AppSettings:
    settings = await get_app_settings(db, user_id)
    if settings is not None:
        return settings

    try:
        async with db.begin_nested():
            created = AppSettings(user_id=user_id)
            db.add(created)
            await db.flush()
        return created
    except IntegrityError:
        result = await db.execute(select(AppSettings).where(_settings_owner_clause(user_id)).limit(1))
        return result.scalar_one()
