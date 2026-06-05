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
