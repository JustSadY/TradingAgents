"""Adversarial coverage hardening tests for TradingAgents Python/FastAPI backend."""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.deps import get_current_user
from backend.core.database import Base, get_db
from backend.core.utils import resolve_benchmark, safe_ticker_component
from backend.main import app
from backend.models.portfolio import Portfolio
from backend.models.settings import AppSettings
from backend.models.user import User


class MockLLMWithTools:
    """Mock for LangChain LLM with bound tools."""

    def __init__(self, content="Mock response", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    async def ainvoke(self, messages):
        """Mock invocation of LLM model."""

        class Response:
            """Mocked response object."""

            def __init__(self, content, tool_calls):
                self.content = content
                self.tool_calls = tool_calls

        return Response(self.content, self.tool_calls)


class MockLLM:
    """Mock for LangChain LLM."""

    def __init__(self, mock_llm_with_tools):
        self.mock_llm_with_tools = mock_llm_with_tools

    def bind_tools(self, tools):
        """Mock tool binding method."""
        return self.mock_llm_with_tools


class MockLLMClient:
    """Mock for custom LLM client wrapper."""

    def __init__(self, mock_llm):
        self.mock_llm = mock_llm

    def get_llm(self):
        """Mock getter for internal LLM."""
        return self.mock_llm


@pytest_asyncio.fixture
async def db_session():
    """Create a clean in-memory SQLite database session for isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_test_data(db_session):
    """Seed necessary test records including a user, settings, and portfolio."""
    from backend.core.security import hash_password

    pwd = hash_password("pass123")
    user = User(username="adversary", hashed_password=pwd, role="user")
    admin = User(username="admin_adversary", hashed_password=pwd, role="admin")
    db_session.add_all([user, admin])
    await db_session.flush()

    settings = AppSettings(user_id=user.id, _watchlist="[]")
    admin_settings = AppSettings(user_id=admin.id, _watchlist="[]")
    db_session.add_all([settings, admin_settings])

    portfolio = Portfolio(
        user_id=user.id,
        mode="simulation",
        broker="mock_broker",
        initial_capital=Decimal("100000"),
        cash_available=Decimal("100000"),
        current_balance=Decimal("100000"),
    )
    db_session.add(portfolio)
    await db_session.commit()
    return user, admin


@pytest_asyncio.fixture
async def test_client(db_session, setup_test_data):
    """FastAPI TestClient with overridden database and user dependencies."""
    user, admin = setup_test_data

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


def test_safe_ticker_component_adversarial():
    """Test boundary inputs and edge cases for safe_ticker_component."""
    assert safe_ticker_component("AAPL") == "AAPL"
    assert safe_ticker_component("AAPL.US") == "AAPL.US"
    assert safe_ticker_component("RELIANCE.NS") == "RELIANCE.NS"
    assert safe_ticker_component("BTC-USD") == "BTC-USD"

    with pytest.raises(ValueError, match="non-empty string"):
        safe_ticker_component("")
    with pytest.raises(ValueError, match="non-empty string"):
        safe_ticker_component(None)
    with pytest.raises(ValueError, match="too long"):
        safe_ticker_component("A" * 33)
    with pytest.raises(ValueError, match="invalid characters"):
        safe_ticker_component("AAPL$")
    with pytest.raises(ValueError, match="invalid characters"):
        safe_ticker_component("AAPL/US")
    with pytest.raises(ValueError, match="invalid characters"):
        safe_ticker_component("AAPL\\US")
    with pytest.raises(ValueError, match="invalid characters"):
        safe_ticker_component("AAPL*")
    with pytest.raises(ValueError, match="invalid characters"):
        safe_ticker_component("AAPL;DROP TABLE")
    with pytest.raises(ValueError, match="must not consist entirely of dots"):
        safe_ticker_component("...")


def test_resolve_benchmark_adversarial():
    """Test resolve_benchmark logic under override, mapping, and default config configurations."""
    assert resolve_benchmark("AAPL", None) == "SPY"
    assert resolve_benchmark("AAPL", {}) == "SPY"

    cfg1 = {"benchmark_ticker": "QQQ"}
    assert resolve_benchmark("AAPL", cfg1) == "QQQ"

    cfg2 = {"benchmark_map": {".NS": "^NSEI", "": "SPY"}}
    assert resolve_benchmark("RELIANCE.NS", cfg2) == "^NSEI"
    assert resolve_benchmark("AAPL", cfg2) == "SPY"

    cfg3 = {"benchmark_map": {".NS": "^NSEI", ".BO": "^BSESN", "": "SPY"}}
    assert resolve_benchmark("RELIANCE.BO", cfg3) == "^BSESN"

    cfg4 = {"benchmark_map": {"": "DIA"}}
    assert resolve_benchmark("AAPL", cfg4) == "DIA"


@pytest.mark.asyncio
async def test_list_portfolio_orders_boundary(test_client):
    """Test API portfolio orders fetch with extreme bounds for limits and offsets."""
    res1 = await test_client.get("/api/portfolio/orders?limit=-1")
    assert res1.status_code == 422

    res2 = await test_client.get("/api/portfolio/orders?limit=0")
    assert res2.status_code == 422

    res3 = await test_client.get("/api/portfolio/orders?limit=201")
    assert res3.status_code == 422

    res4 = await test_client.get("/api/portfolio/orders?offset=-1")
    assert res4.status_code == 422


@pytest.mark.asyncio
async def test_execute_order_validation_adversarial(test_client):
    """Test paper order creation under various parameter combinations and payload boundaries."""
    payload1 = {"ticker": "", "action": "BUY", "quantity": 10.0, "leverage": 1.0, "allow_short": False}
    res1 = await test_client.post("/api/trading/order", json=payload1)
    assert res1.status_code == 422

    payload2 = {"ticker": "AAPL", "action": "INVALID", "quantity": 10.0, "leverage": 1.0, "allow_short": False}
    res2 = await test_client.post("/api/trading/order", json=payload2)
    assert res2.status_code == 422

    payload3 = {"ticker": "AAPL", "action": "BUY", "quantity": 0.0, "leverage": 1.0, "allow_short": False}
    res3 = await test_client.post("/api/trading/order", json=payload3)
    assert res3.status_code == 422

    payload4 = {"ticker": "AAPL", "action": "BUY", "quantity": -5.0, "leverage": 1.0, "allow_short": False}
    res4 = await test_client.post("/api/trading/order", json=payload4)
    assert res4.status_code == 422

    payload5 = {"ticker": "AAPL", "action": "BUY", "quantity": 10.0, "leverage": 0.9, "allow_short": False}
    res5 = await test_client.post("/api/trading/order", json=payload5)
    assert res5.status_code == 422

    payload6 = {"ticker": "AAPL", "action": "BUY", "quantity": 10.0, "leverage": 10.1, "allow_short": False}
    res6 = await test_client.post("/api/trading/order", json=payload6)
    assert res6.status_code == 422


@pytest.mark.asyncio
async def test_alert_lifecycle_adversarial(test_client):
    """Test alert creation limits, invalid inputs, updates, and deletes for non-existent alerts."""
    payload1 = {"ticker": "AAPL", "condition": "above", "target_price": -1.0, "auto_analyze": False}
    res1 = await test_client.post("/api/alerts", json=payload1)
    assert res1.status_code == 422

    payload2 = {"ticker": "AAPL", "condition": "equal", "target_price": 150.0, "auto_analyze": False}
    res2 = await test_client.post("/api/alerts", json=payload2)
    assert res2.status_code == 422

    res3 = await test_client.patch("/api/alerts/99999", json={"target_price": 160.0})
    assert res3.status_code == 404

    res4 = await test_client.delete("/api/alerts/99999")
    assert res4.status_code == 404


@pytest.mark.asyncio
async def test_assistant_chat_adversarial(test_client, db_session, setup_test_data, monkeypatch):
    """Test assistant chat history, message boundaries, and LLM provider checks."""
    user, admin = setup_test_data

    res_hist_empty = await test_client.get("/api/assistant/history")
    assert res_hist_empty.status_code == 200
    assert res_hist_empty.json() == []

    res_chat_long = await test_client.post("/api/assistant/chat", json={"message": "a" * 2001})
    assert res_chat_long.status_code == 422

    res_chat_empty = await test_client.post("/api/assistant/chat", json={"message": ""})
    assert res_chat_empty.status_code == 422

    import backend.trading_agents.llm_clients.factory as factory_mod

    mock_tools = MockLLMWithTools(content="I can help with that.")
    mock_llm = MockLLM(mock_tools)
    mock_client = MockLLMClient(mock_llm)

    def fake_create_llm_client(*args, **kwargs):
        return mock_client

    monkeypatch.setattr(factory_mod, "create_llm_client", fake_create_llm_client)

    res_chat_ok = await test_client.post("/api/assistant/chat", json={"message": "Hello Assistant"})
    assert res_chat_ok.status_code == 200
    assert "content" in res_chat_ok.json()
    assert res_chat_ok.json()["content"] == "I can help with that."

    res_hist_after = await test_client.get("/api/assistant/history")
    assert res_hist_after.status_code == 200
    history = res_hist_after.json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    res_clear = await test_client.delete("/api/assistant/history")
    assert res_clear.status_code == 204

    res_hist_cleared = await test_client.get("/api/assistant/history")
    assert res_hist_cleared.status_code == 200
    assert res_hist_cleared.json() == []
