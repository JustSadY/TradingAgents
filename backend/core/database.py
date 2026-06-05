from sqlalchemy import Numeric, text
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
async def _has_alembic_version(conn) -> bool:
    if conn.dialect.name == "sqlite":
        row = (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ))).fetchone()
        return row is not None
    row = (await conn.execute(text(
        "SELECT to_regclass('public.alembic_version')"
    ))).scalar_one_or_none()
    return row is not None


async def create_all_tables():
    import backend.models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if await _has_alembic_version(conn):
            return
        from backend.core.migrations import apply_column_migrations, apply_type_migrations
        await apply_column_migrations(conn)
        await apply_type_migrations(conn)
