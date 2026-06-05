from sqlalchemy import Numeric
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings
settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Exact fixed-precision column type for monetary / price / quantity values.
# Stored as PostgreSQL NUMERIC(20, 8) (exact) instead of lossy double precision.
# `asdecimal=True` maps Python-side values to `Decimal` type to avoid
# rounding/accumulative floating-point errors. Arithmetic in the trading
# services uses Python `Decimal` end-to-end.
MONEY = Numeric(20, 8, asdecimal=True)


class Base(DeclarativeBase):
    pass
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
async def create_all_tables():
    import backend.models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from backend.core.migrations import apply_column_migrations, apply_type_migrations
        await apply_column_migrations(conn)
        await apply_type_migrations(conn)
