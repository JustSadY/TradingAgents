import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.core.database import Base
from backend.core.migrations import apply_column_migrations, apply_type_migrations
import backend.core.database as db_module
from backend.models.news_cache import NewsAnalysisCache
from backend.trading_agents.agents.sub.analysts.news_analyst import create_news_analyst
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

class FakeLLM(Runnable):
    def __init__(self):
        self.invocations = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, input, config=None, **kwargs):
        raise NotImplementedError("Use ainvoke instead")

    async def ainvoke(self, input, config=None, **kwargs):
        self.invocations += 1
        class Response:
            content = f"Mock analysis content {self.invocations}"
            tool_calls = []
        return Response()

@pytest.mark.anyio
async def test_news_analyst_caching_lifecycle(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_column_migrations(conn)
        await apply_type_migrations(conn)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", Session)

    llm = FakeLLM()
    node = create_news_analyst(llm)

    state = {
        "company_of_interest": "MSFT",
        "trade_date": "2026-06-23",
        "asset_type": "stock",
        "messages": [],
    }

    mock_news = "Microsoft launches new AI model."
    mock_global = "Markets are stable today."
    mock_insider = "CEO sold 1000 shares."

    async def side_effect(func_name, *args, **kwargs):
        if func_name == "get_news":
            return mock_news
        if func_name == "get_global_news":
            return mock_global
        if func_name == "get_insider_transactions":
            return mock_insider
        return ""

    with patch("backend.trading_agents.dataflows.interface.route_to_vendor", side_effect=side_effect):
        res1 = await node(state)
        assert res1 is not None
        assert "news_report" in res1
        assert "Mock analysis content 1" in res1["news_report"]
        assert llm.invocations == 1

        async with Session() as db:
            stmt = select(NewsAnalysisCache).where(NewsAnalysisCache.ticker == "MSFT")
            db_res = await db.execute(stmt)
            entry = db_res.scalar_one_or_none()
            assert entry is not None
            assert entry.analysis_result == res1["news_report"]

        res2 = await node(state)
        assert res2 is not None
        assert "news_report" in res2
        assert "Mock analysis content 1" in res2["news_report"]
        assert llm.invocations == 1

        state_diff = {
            "company_of_interest": "MSFT",
            "trade_date": "2026-06-24",
            "asset_type": "stock",
            "messages": [],
        }
        res3 = await node(state_diff)
        assert res3 is not None
        assert "Mock analysis content 2" in res3["news_report"]
        assert llm.invocations == 2

    await engine.dispose()
