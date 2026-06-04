from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings
settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
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
    import backend.models.user
    import backend.models.settings
    import backend.models.system_settings
    import backend.models.page_permission
    import backend.models.analysis
    import backend.models.portfolio
    import backend.models.order
    import backend.models.log
    import backend.models.alert
    import backend.models.preset
    import backend.models.portfolio_analysis
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from backend.core.migrations import apply_column_migrations
        await apply_column_migrations(conn)
