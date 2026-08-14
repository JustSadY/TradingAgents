import os
import tempfile
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.setdefault("TRADINGAGENTS_LOG_DIR", "/tmp")
os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR", "/tmp/ta_cache")
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", "/tmp/ta_results")
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["METRICS_TOKEN"] = "test-metrics-token"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = ""
os.environ["REDIS_URL"] = ""
os.environ["ANALYSIS_QUEUE_MODE"] = "inline"

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import backend.bootstrap  # noqa: F401, E402
import backend.models.agent_settings  # noqa: F401, E402
import backend.models.alert  # noqa: F401, E402
import backend.models.analysis  # noqa: F401, E402
import backend.models.asset_strategy  # noqa: F401, E402
import backend.models.assistant  # noqa: F401, E402
import backend.models.log  # noqa: F401, E402
import backend.models.market_summary  # noqa: F401, E402
import backend.models.news_cache  # noqa: F401, E402
import backend.models.order  # noqa: F401, E402
import backend.models.page_permission  # noqa: F401, E402
import backend.models.persona  # noqa: F401, E402
import backend.models.portfolio  # noqa: F401, E402
import backend.models.portfolio_analysis  # noqa: F401, E402
import backend.models.preset  # noqa: F401, E402
import backend.models.settings  # noqa: F401, E402
import backend.models.shared_report  # noqa: F401, E402
import backend.models.system_settings  # noqa: F401, E402
import backend.models.tool_settings  # noqa: F401, E402
import backend.models.trade_note  # noqa: F401, E402
import backend.models.user  # noqa: F401, E402
import backend.models.webhook_delivery  # noqa: F401, E402
from backend.core.database import Base, get_db  # noqa: E402
from backend.core.security import create_access_token, hash_password  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.user import User  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{_TEST_DB_PATH}",
        echo=False,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, Any]:
    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()

@pytest_asyncio.fixture
async def db(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Compatibility alias that shares the canonical per-test transaction.

    Assigning ``db = db_session`` registers two independent pytest fixtures.
    A test that requests ``db`` while ``test_user`` requests ``db_session``
    then opens two uncommitted SQLite write transactions, producing a
    non-deterministic ``database is locked`` failure.  Make the alias depend
    on ``db_session`` so pytest's fixture cache gives every dependent fixture
    the exact same session/transaction.
    """
    yield db_session

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, Any]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        username="testuser",
        hashed_password=hash_password("testpass123"),
        is_active=True,
        role="user",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        username="admin",
        hashed_password=hash_password("adminpass123"),
        is_active=True,
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user

@pytest.fixture
def auth_token(test_user: User) -> str:
    return create_access_token(username=test_user.username, role=test_user.role, token_version=0)

@pytest.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(username=admin_user.username, role=admin_user.role, token_version=0)

@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}

@pytest_asyncio.fixture
async def authenticated_client(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> AsyncClient:
    """Authenticated client with the broad access endpoint-behaviour tests need.

    Page/section permissions are deny-by-default in production.  Most older
    API tests exercise endpoint behaviour rather than RBAC, so grant this
    dedicated convenience fixture every page and settings section.  Security
    tests should deliberately use ``async_client`` + ``auth_headers`` instead
    to start from a user with no entitlement rows.
    """
    from backend.core.constants import PAGE_KEYS, SETTING_KEYS
    from backend.models.page_permission import UserPagePermission, UserSettingPermission

    db_session.add_all(
        [UserPagePermission(user_id=test_user.id, page_key=key, allowed=True) for key in PAGE_KEYS if key != "settings"]
        + [UserSettingPermission(user_id=test_user.id, setting_key=key, allowed=True) for key in SETTING_KEYS]
    )
    await db_session.flush()
    async_client.headers.update(auth_headers)
    return async_client

auth_client = authenticated_client

@pytest.fixture
def mock_llm(mocker):
    mock = mocker.patch("backend.trading_agents.llm_clients.registry.get_llm")
    mock_instance = mocker.AsyncMock()
    mock_instance.invoke.return_value = "Mocked LLM response"
    mock.return_value = mock_instance
    return mock
