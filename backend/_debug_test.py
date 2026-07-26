"""Debug script for auth test failure."""
import asyncio
import os
import tempfile

os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("TRADINGAGENTS_LOG_DIR", "/tmp")
os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR", "/tmp/ta_cache")
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", "/tmp/ta_results")

fd, db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["METRICS_TOKEN"] = "test-metrics-token"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = ""

import backend.bootstrap  # noqa: F401, E402
from backend.core.database import Base, get_db  # noqa: E402
from backend.core.security import hash_password  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.user import User  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import NullPool, event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

# Ensure models are imported
import backend.models.agent_settings  # noqa: F401,E402
import backend.models.alert  # noqa: F401,E402
import backend.models.analysis  # noqa: F401,E402
import backend.models.assistant  # noqa: F401,E402
import backend.models.log  # noqa: F401,E402
import backend.models.market_summary  # noqa: F401,E402
import backend.models.news_cache  # noqa: F401,E402
import backend.models.order  # noqa: F401,E402
import backend.models.page_permission  # noqa: F401,E402
import backend.models.persona  # noqa: F401,E402
import backend.models.portfolio  # noqa: F401,E402
import backend.models.portfolio_analysis  # noqa: F401,E402
import backend.models.preset  # noqa: F401,E402
import backend.models.settings  # noqa: F401,E402
import backend.models.shared_report  # noqa: F401,E402
import backend.models.system_settings  # noqa: F401,E402
import backend.models.tool_settings  # noqa: F401,E402
import backend.models.trade_note  # noqa: F401,E402
import backend.models.user  # noqa: F401,E402
import backend.models.webhook_delivery  # noqa: F401,E402


async def main():
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    user = User(
        username="logintest",
        hashed_password=hash_password("correctpass"),
        email="login@example.com",
        role="user",
        is_active=True,
    )
    session.add(user)
    await session.flush()

    async def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/login",
            json={"username": "logintest", "password": "correctpass"},
        )
        print("Status:", resp.status_code)
        print("Body:", resp.text[:1000])
        print("Headers:", dict(resp.headers))

    app.dependency_overrides.clear()
    await session.close()
    await transaction.rollback()
    await connection.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())