from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.page_permission import UserPagePermission, UserSettingPermission


async def get_user_page_permission(db: AsyncSession, user_id: int, page_key: str):
    res = await db.execute(
        select(UserPagePermission)
        .where(UserPagePermission.user_id == user_id)
        .where(UserPagePermission.page_key == page_key)
    )
    return res.scalar_one_or_none()


async def list_allowed_page_keys(db: AsyncSession, user_id: int) -> set[str]:
    res = await db.execute(
        select(UserPagePermission)
        .where(UserPagePermission.user_id == user_id)
        .where(UserPagePermission.allowed == True)
    )
    return {r.page_key for r in res.scalars().all()}


async def get_user_setting_permission(db: AsyncSession, user_id: int, setting_key: str):
    res = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user_id)
        .where(UserSettingPermission.setting_key == setting_key)
    )
    return res.scalar_one_or_none()


async def list_allowed_setting_sections(db: AsyncSession, user_id: int) -> set[str]:
    res = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user_id)
        .where(UserSettingPermission.allowed == True)
    )
    return {r.setting_key for r in res.scalars().all()}

async def get_user_page_permissions_map(db: AsyncSession, user_id: int) -> dict[str, bool]:
    result = await db.execute(
        select(UserPagePermission).where(UserPagePermission.user_id == user_id)
    )
    return {p.page_key: p.allowed for p in result.scalars().all()}

async def get_user_setting_permissions_map(db: AsyncSession, user_id: int) -> dict[str, bool]:
    result = await db.execute(
        select(UserSettingPermission).where(UserSettingPermission.user_id == user_id)
    )
    return {p.setting_key: p.allowed for p in result.scalars().all()}

async def set_user_page_permission(db: AsyncSession, user_id: int, page_key: str, allowed: bool) -> None:
    result = await db.execute(
        select(UserPagePermission)
        .where(UserPagePermission.user_id == user_id)
        .where(UserPagePermission.page_key == page_key)
    )
    perm = result.scalar_one_or_none()
    if perm is None:
        db.add(UserPagePermission(user_id=user_id, page_key=page_key, allowed=allowed))
    else:
        perm.allowed = allowed

async def set_user_setting_permission(db: AsyncSession, user_id: int, setting_key: str, allowed: bool) -> None:
    result = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user_id)
        .where(UserSettingPermission.setting_key == setting_key)
    )
    perm = result.scalar_one_or_none()
    if perm is None:
        db.add(UserSettingPermission(user_id=user_id, setting_key=setting_key, allowed=allowed))
    else:
        perm.allowed = allowed
