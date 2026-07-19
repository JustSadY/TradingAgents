"""Test data factories for creating model instances."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.models.analysis import AnalysisResult
from backend.models.user import User


async def create_user(
    db: AsyncSession,
    username: str = "factoryuser",
    password: str = "password123",
    role: str = "user",
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        hashed_password=hash_password(password),
        is_active=is_active,
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def create_analysis(
    db: AsyncSession,
    user_id: int,
    ticker: str = "AAPL",
    signal: str = "buy",
    status: str = "completed",
    **kwargs,
) -> AnalysisResult:
    analysis = AnalysisResult(
        user_id=user_id,
        ticker=ticker,
        trade_date="2026-01-15",
        signal=signal,
        status=status,
        **kwargs,
    )
    db.add(analysis)
    await db.flush()
    await db.refresh(analysis)
    return analysis
