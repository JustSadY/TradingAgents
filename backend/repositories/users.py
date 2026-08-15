"""Data-access helpers for the User model."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def username_exists(db: AsyncSession, username: str, exclude_user_id: int | None = None) -> bool:
    query = select(User.id).where(User.username == username)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

async def email_exists(db: AsyncSession, email: str, exclude_user_id: int | None = None) -> bool:
    query = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

async def list_users(db: AsyncSession) -> list[User]:
    """List all users ordered by ID."""
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())

async def create_user_with_permissions(
    db: AsyncSession, username: str, hashed_password: str, email: str | None, display_name: str | None, role: str
) -> User:
    from backend.core.constants import SETTING_KEYS
    from backend.models.page_permission import UserPagePermission, UserSettingPermission

    user = User(
        username=username,
        hashed_password=hashed_password,
        email=email,
        display_name=display_name,
        role=role,
    )
    db.add(user)
    await db.flush()

    db.add(UserPagePermission(user_id=user.id, page_key="dashboard", allowed=True))
    db.add(UserPagePermission(user_id=user.id, page_key="portfolio", allowed=True))

    for s_key in SETTING_KEYS:
        db.add(UserSettingPermission(user_id=user.id, setting_key=s_key, allowed=True))

    await db.flush()
    return user

async def update_user_profile(
    db: AsyncSession,
    user: User,
    email: str | None = None,
    display_name: str | None = None,
    hashed_password: str | None = None,
) -> User:
    """Update a user's basic profile fields."""
    if email is not None:
        user.email = email
    if display_name is not None:
        user.display_name = display_name
    if hashed_password is not None:
        user.hashed_password = hashed_password
    await db.flush()
    return user

async def update_user_admin(
    db: AsyncSession,
    user: User,
    role: str | None = None,
    is_active: bool | None = None,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    """Update a user's administrative fields."""
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if email is not None:
        user.email = email
    if display_name is not None:
        user.display_name = display_name
    await db.flush()
    return user
