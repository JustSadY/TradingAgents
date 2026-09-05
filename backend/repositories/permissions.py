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


async def list_user_page_permission_rows(db: AsyncSession, user_id: int) -> list[UserPagePermission]:
    result = await db.execute(select(UserPagePermission).where(UserPagePermission.user_id == user_id))
    return list(result.scalars().all())


async def list_allowed_page_keys(db: AsyncSession, user_id: int) -> set[str]:
    res = await db.execute(
        select(UserPagePermission)
        .where(UserPagePermission.user_id == user_id)
        .where(UserPagePermission.allowed.is_(True))
    )
    return {r.page_key for r in res.scalars().all()}


async def get_user_setting_permission(db: AsyncSession, user_id: int, setting_key: str):
    res = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user_id)
        .where(UserSettingPermission.setting_key == setting_key)
    )
    return res.scalar_one_or_none()


async def list_user_setting_permission_rows(db: AsyncSession, user_id: int) -> list[UserSettingPermission]:
    result = await db.execute(select(UserSettingPermission).where(UserSettingPermission.user_id == user_id))
    return list(result.scalars().all())


async def list_allowed_setting_sections(db: AsyncSession, user_id: int) -> set[str]:
    res = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user_id)
        .where(UserSettingPermission.allowed.is_(True))
    )
    return {r.setting_key for r in res.scalars().all()}


async def get_user_page_permissions_map(db: AsyncSession, user_id: int) -> dict[str, bool]:
    return {p.page_key: p.allowed for p in await list_user_page_permission_rows(db, user_id)}


async def get_user_setting_permissions_map(db: AsyncSession, user_id: int) -> dict[str, bool]:
    return {p.setting_key: p.allowed for p in await list_user_setting_permission_rows(db, user_id)}


def ensure_user_page_permission_row(
    db: AsyncSession,
    *,
    row: UserPagePermission | None,
    user_id: int,
    page_key: str,
) -> UserPagePermission:
    if row is not None:
        return row
    row = UserPagePermission(user_id=user_id, page_key=page_key, allowed=False)
    db.add(row)
    return row


def ensure_user_setting_permission_row(
    db: AsyncSession,
    *,
    row: UserSettingPermission | None,
    user_id: int,
    setting_key: str,
) -> UserSettingPermission:
    if row is not None:
        return row
    row = UserSettingPermission(user_id=user_id, setting_key=setting_key, allowed=False)
    db.add(row)
    return row


async def set_user_page_permission(db: AsyncSession, user_id: int, page_key: str, allowed: bool) -> None:
    perm = await get_user_page_permission(db, user_id, page_key)
    perm = ensure_user_page_permission_row(db, row=perm, user_id=user_id, page_key=page_key)
    perm.allowed = allowed


async def set_user_setting_permission(db: AsyncSession, user_id: int, setting_key: str, allowed: bool) -> None:
    perm = await get_user_setting_permission(db, user_id, setting_key)
    perm = ensure_user_setting_permission_row(db, row=perm, user_id=user_id, setting_key=setting_key)
    perm.allowed = allowed
