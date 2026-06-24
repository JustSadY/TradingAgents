import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.core.database import Base
from backend.core.migrations import apply_column_migrations, apply_type_migrations
import backend.core.database as db_module
from backend.models.news_cache import AnalystReportCache
from backend.trading_agents.agents.sub.analysts.fundamentals_analyst import create_fundamentals_analyst
from backend.trading_agents.agents.sub.analysts.market_analyst import create_market_analyst
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
async def test_fundamentals_and_market_caching_lifecycle(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_column_migrations(conn)
        await apply_type_migrations(conn)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", Session)

    llm = FakeLLM()
    fund_node = create_fundamentals_analyst(llm)
    market_node = create_market_analyst(llm)

    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-06-23",
        "asset_type": "stock",
        "messages": [],
    }

    mock_fundamentals = "Apple Inc. sector: Tech, PE: 30."
    mock_balance_sheet = "Total assets: 350B."
    mock_cashflow = "Free cash flow: 80B."
    mock_income = "Net income: 95B."
    mock_sec = "10-Q filing 2026."
    mock_insider = "CEO bought 5000 shares."

    mock_stock = "Historical Close: 165.0, Volume: 50M."
    mock_indicators = "RSI: 55, MACD: 1.2."

    async def side_effect(func_name, *args, **kwargs):
        if func_name == "get_fundamentals":
            return mock_fundamentals
        if func_name == "get_balance_sheet":
            return mock_balance_sheet
        if func_name == "get_cashflow":
            return mock_cashflow
        if func_name == "get_income_statement":
            return mock_income
        if func_name == "get_sec_filings":
            return mock_sec
        if func_name == "get_insider_transactions":
            return mock_insider
        if func_name == "get_stock_data":
            return mock_stock
        if func_name == "get_indicators":
            return mock_indicators
        return ""

    with patch("backend.trading_agents.dataflows.interface.route_to_vendor", side_effect=side_effect):
        # 1. Test Fundamentals Analyst Cache Miss & Hit
        res_f1 = await fund_node(state)
        assert res_f1 is not None
        assert "fundamentals_report" in res_f1
        assert "Mock analysis content 1" in res_f1["fundamentals_report"]
        assert llm.invocations == 1

        async with Session() as db:
            stmt = select(AnalystReportCache).where(
                AnalystReportCache.analyst_key == "fundamentals",
                AnalystReportCache.ticker == "AAPL"
            )
            db_res = await db.execute(stmt)
            entry = db_res.scalar_one_or_none()
            assert entry is not None
            assert entry.analysis_result == res_f1["fundamentals_report"]

        res_f2 = await fund_node(state)
        assert res_f2 is not None
        assert "fundamentals_report" in res_f2
        assert "Mock analysis content 1" in res_f2["fundamentals_report"]
        assert llm.invocations == 1

        # 2. Test Market Analyst Cache Miss & Hit
        res_m1 = await market_node(state)
        assert res_m1 is not None
        assert "market_report" in res_m1
        assert "Mock analysis content 2" in res_m1["market_report"]
        assert llm.invocations == 2

        async with Session() as db:
            stmt = select(AnalystReportCache).where(
                AnalystReportCache.analyst_key == "market",
                AnalystReportCache.ticker == "AAPL"
            )
            db_res = await db.execute(stmt)
            entry = db_res.scalar_one_or_none()
            assert entry is not None
            assert entry.analysis_result == res_m1["market_report"]

        res_m2 = await market_node(state)
        assert res_m2 is not None
        assert "market_report" in res_m2
        assert "Mock analysis content 2" in res_m2["market_report"]
        assert llm.invocations == 2

    await engine.dispose()
