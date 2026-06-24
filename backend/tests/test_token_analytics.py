from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.deps import get_current_user
from backend.core.database import Base, get_db
from backend.main import app
from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.repositories import token_analytics as repo
from backend.services import token_analytics_service


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db):
    u = User(username="testuser", hashed_password="abc", role="user")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_estimate_cost():
    assert token_analytics_service.estimate_cost("ollama", "llama3", 100, 200) == 0.0
    assert token_analytics_service.estimate_cost("openai", "gpt-4o", 1000000, 1000000) == 20.0
    assert token_analytics_service.estimate_cost("unknown", "unknown", 1000000, 1000000) == 10.0


@pytest.mark.asyncio
async def test_token_analytics_queries_and_service(db, user):
    ar1 = AnalysisResult(
        user_id=user.id,
        ticker="AAPL",
        trade_date="2026-06-20",
        llm_provider="openai",
        llm_model="gpt-4o",
        tokens_in=10000,
        tokens_out=5000,
        status="completed",
        created_at=datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC),
    )
    ar2 = AnalysisResult(
        user_id=user.id,
        ticker="MSFT",
        trade_date="2026-06-20",
        llm_provider="ollama",
        llm_model="llama3",
        tokens_in=20000,
        tokens_out=10000,
        status="completed",
        created_at=datetime(2026, 6, 20, 13, 0, 0, tzinfo=UTC),
    )
    ar3 = AnalysisResult(
        user_id=user.id,
        ticker="TSLA",
        trade_date="2026-06-20",
        llm_provider="openai",
        llm_model="gpt-4o",
        tokens_in=5000,
        tokens_out=2000,
        status="failed",
        created_at=datetime(2026, 6, 20, 14, 0, 0, tzinfo=UTC),
    )
    db.add_all([ar1, ar2, ar3])
    await db.commit()

    rows = await repo.get_token_usage_rows(db, user.id)
    assert len(rows) == 2

    daily_rows = await repo.get_daily_token_usage_rows(db, user.id)
    assert len(daily_rows) == 1

    analytics = await token_analytics_service.get_token_analytics(db, user.id)
    assert analytics["total_tokens_in"] == 30000
    assert analytics["total_tokens_out"] == 15000
    assert analytics["total_tokens"] == 45000
    assert len(analytics["breakdown"]) == 2
    assert analytics["breakdown"][0]["provider"] == "openai"
    assert analytics["breakdown"][0]["model"] == "gpt-4o"
    assert analytics["breakdown"][1]["provider"] == "ollama"


@pytest.mark.asyncio
async def test_token_analytics_endpoint(db, user, monkeypatch):
    ar = AnalysisResult(
        user_id=user.id,
        ticker="AAPL",
        trade_date="2026-06-20",
        llm_provider="openai",
        llm_model="gpt-4o",
        tokens_in=1000000,
        tokens_out=1000000,
        status="completed",
        created_at=datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC),
    )
    db.add(ar)
    await db.commit()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    response = client.get("/api/analytics/token-usage")
    assert response.status_code == 200

    data = response.json()
    assert data["total_tokens_in"] == 1000000
    assert data["total_tokens_out"] == 1000000
    assert data["total_cost_usd"] == 20.0

    app.dependency_overrides.clear()
