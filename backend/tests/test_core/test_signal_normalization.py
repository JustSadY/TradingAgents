from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.core.migrations import normalize_sqlite_analysis_signals

async def test_sqlite_signal_normalization_rewrites_only_known_legacy_values() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY, signal TEXT)"))
            await conn.execute(
                text(
                    """
                    INSERT INTO analysis_results (id, signal) VALUES
                    (1, 'buy'),
                    (2, '  SELL  '),
                    (3, 'Hold'),
                    (4, 'legacy-free-text'),
                    (5, NULL)
                    """
                )
            )

            await normalize_sqlite_analysis_signals(conn)
            rows = (await conn.execute(text("SELECT signal FROM analysis_results ORDER BY id"))).scalars().all()

        assert rows == ["Buy", "Sell", "Hold", "legacy-free-text", None]
    finally:
        await engine.dispose()
