import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_e2e_db.sqlite"
os.environ["ENVIRONMENT"] = "development"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = ""

from backend.core.config import get_settings

get_settings.cache_clear()

from backend.core.limiter import limiter

limiter.enabled = False

from backend.services.cron_service import CronService

CronService.start = lambda self: None

import pandas as pd
import yfinance as yf


def mock_yf_download(tickers, *args, **kwargs):
    if isinstance(tickers, str):
        ticker_list = tickers.split()
    else:
        ticker_list = list(tickers)

    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="D")

    if len(ticker_list) > 1:
        cols = pd.MultiIndex.from_product([ticker_list, ["Open", "High", "Low", "Close", "Volume"]])
        df = pd.DataFrame(100.0, index=dates, columns=cols)
        for t in ticker_list:
            df[(t, "Volume")] = 10000.0
    else:
        cols = ["Open", "High", "Low", "Close", "Volume"]
        df = pd.DataFrame(100.0, index=dates, columns=cols)
        df["Volume"] = 10000.0
    return df


class DummyTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, *args, **kwargs):
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="D")
        return pd.DataFrame(
            {
                "Open": [100.0] * 100,
                "High": [105.0] * 100,
                "Low": [95.0] * 100,
                "Close": [100.0] * 100,
                "Volume": [10000.0] * 100,
            },
            index=dates,
        )


yf.download = mock_yf_download
yf.Ticker = DummyTicker

LIVE_PRICES = {
    "AAPL": 150.0,
    "MSFT": 300.0,
    "SPY": 400.0,
    "TSLA": 200.0,
    "GOOG": 100.0,
}


async def mock_get_live_price(ticker: str) -> float | None:
    t = ticker.upper()
    return LIVE_PRICES.get(t, 100.0)


async def mock_get_live_prices_batch(tickers: list[str]) -> dict[str, float]:
    return {t.upper(): LIVE_PRICES.get(t.upper(), 100.0) for t in tickers}


async def mock_get_live_prices_details_batch(tickers: list[str]) -> dict[str, dict[str, float]]:
    return {t.upper(): {"price": LIVE_PRICES.get(t.upper(), 100.0), "change_percent": 0.0} for t in tickers}


async def mock_get_historical_data(ticker: str, start_date: str, end_date: str):
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0] * len(dates),
            "High": [105.0] * len(dates),
            "Low": [95.0] * len(dates),
            "Close": [101.0] * len(dates),
            "Volume": [10000.0] * len(dates),
        },
        index=dates,
    )
    return df


from backend.core.database import AsyncSessionLocal
from backend.models.analysis import AnalysisResult
from backend.models.portfolio_analysis import MultiTickerAnalysis


async def mock_run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings,
    db,
    triggered_by: str = "manual",
    task_id: str | None = None,
    user=None,
):
    import uuid

    if not task_id:
        task_id = str(uuid.uuid4())
    res = AnalysisResult(
        user_id=user.id if user else None,
        ticker=ticker.upper(),
        trade_date=trade_date,
        asset_type=asset_type,
        signal="Buy",
        market_report="Mock Market Report",
        sentiment_report="Mock Sentiment Report",
        news_report="Mock News Report",
        fundamentals_report="Mock Fundamentals Report",
        final_decision="Mock Final Decision: BUY",
        task_id=task_id,
        status="completed",
    )
    db.add(res)
    await db.flush()
    return task_id, res


async def mock_run_analysis_task(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings,
    task_id: str,
    user=None,
) -> None:
    async with AsyncSessionLocal() as db:
        await mock_run_analysis(ticker, trade_date, asset_type, settings, db, "manual", task_id, user)
        await db.commit()


async def mock_run_portfolio_task(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings,
    user=None,
    task_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        analysis_ids = []
        for ticker in tickers:
            _, res = await mock_run_analysis(ticker, trade_date, asset_type, settings, db, "manual", None, user)
            analysis_ids.append(res.id)

        p_res = MultiTickerAnalysis(
            user_id=user.id if user else None,
            trade_date=trade_date,
            asset_type=asset_type,
            super_portfolio_report="Mock Super Portfolio Report",
            triggered_by="manual",
        )
        p_res.tickers = tickers
        p_res.analysis_ids = analysis_ids
        db.add(p_res)
        await db.commit()


async def mock_generate_formula(db, prompt: str, user) -> str:
    return "(Close - SMA(20)) / STD(20)"


async def mock_get_rebalance_suggestions(db, user) -> dict:
    return {
        "summary": "Mock rebalance summary",
        "score": 85,
        "issues": ["Mock concentration warning"],
        "suggestions": [
            {
                "action": "BUY",
                "ticker": "AAPL",
                "quantity": 10.0,
                "rationale": "Mock buy rationale",
                "urgency": "medium",
            }
        ],
    }


import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import backend.api.analysis as api_ans
import backend.api.watchlist as wl
import backend.services.alert_service as als
import backend.services.analysis_service as ans
import backend.services.cron_service as crs
import backend.services.formula_assist_service as fas
import backend.services.market_data_service as mds
import backend.services.market_service as ms
import backend.services.mock_trading_service as mts
import backend.services.performance_service as ps
import backend.services.portfolio_assistant_service as pas
import backend.services.portfolio_rebalance_service as prs
from backend.main import app


@pytest.fixture(autouse=True)
def mock_e2e_services_fixture():
    originals = {}

    originals[(mds, "get_live_price")] = getattr(mds, "get_live_price", None)
    originals[(mds, "get_live_prices_batch")] = getattr(mds, "get_live_prices_batch", None)
    originals[(mds, "get_live_prices_details_batch")] = getattr(mds, "get_live_prices_details_batch", None)
    originals[(mds, "get_historical_data")] = getattr(mds, "get_historical_data", None)

    originals[(als, "get_live_prices_batch")] = getattr(als, "get_live_prices_batch", None)
    originals[(wl, "get_live_prices_details_batch")] = getattr(wl, "get_live_prices_details_batch", None)
    originals[(mts, "get_live_price")] = getattr(mts, "get_live_price", None)
    originals[(mts, "get_live_prices_batch")] = getattr(mts, "get_live_prices_batch", None)
    originals[(ps, "get_live_prices_batch")] = getattr(ps, "get_live_prices_batch", None)
    originals[(pas, "get_live_prices_batch")] = getattr(pas, "get_live_prices_batch", None)
    originals[(ms, "get_live_price")] = getattr(ms, "get_live_price", None)

    originals[(ans, "run_analysis")] = getattr(ans, "run_analysis", None)
    originals[(ans, "run_analysis_task")] = getattr(ans, "run_analysis_task", None)
    originals[(ans, "run_portfolio_task")] = getattr(ans, "run_portfolio_task", None)

    originals[(als, "run_analysis")] = getattr(als, "run_analysis", None)
    originals[(crs, "run_analysis")] = getattr(crs, "run_analysis", None)
    originals[(pas, "run_analysis")] = getattr(pas, "run_analysis", None)

    originals[(api_ans, "run_analysis")] = getattr(api_ans, "run_analysis", None)
    originals[(api_ans, "run_analysis_task")] = (
        getattr(api_ans, "run_analysis_task", None) if hasattr(api_ans, "run_analysis_task") else None
    )
    originals[(api_ans, "run_portfolio_task")] = (
        getattr(api_ans, "run_portfolio_task", None) if hasattr(api_ans, "run_portfolio_task") else None
    )

    aq = None
    try:
        import backend.services.analysis_queue as aq_mod

        aq = aq_mod
        originals[(aq, "run_analysis")] = getattr(aq, "run_analysis", None) if hasattr(aq, "run_analysis") else None
    except ImportError:
        pass

    originals[(fas, "generate_formula")] = getattr(fas, "generate_formula", None)
    originals[(prs, "get_rebalance_suggestions")] = getattr(prs, "get_rebalance_suggestions", None)

    mds.get_live_price = mock_get_live_price
    mds.get_live_prices_batch = mock_get_live_prices_batch
    mds.get_live_prices_details_batch = mock_get_live_prices_details_batch
    mds.get_historical_data = mock_get_historical_data

    als.get_live_prices_batch = mock_get_live_prices_batch
    wl.get_live_prices_details_batch = mock_get_live_prices_details_batch
    mts.get_live_price = mock_get_live_price
    mts.get_live_prices_batch = mock_get_live_prices_batch
    ps.get_live_prices_batch = mock_get_live_prices_batch
    pas.get_live_prices_batch = mock_get_live_prices_batch
    ms.get_live_price = mock_get_live_price

    ans.run_analysis = mock_run_analysis
    ans.run_analysis_task = mock_run_analysis_task
    ans.run_portfolio_task = mock_run_portfolio_task

    als.run_analysis = mock_run_analysis
    crs.run_analysis = mock_run_analysis
    pas.run_analysis = mock_run_analysis

    api_ans.run_analysis = mock_run_analysis
    if hasattr(api_ans, "run_analysis_task"):
        api_ans.run_analysis_task = mock_run_analysis_task
    if hasattr(api_ans, "run_portfolio_task"):
        api_ans.run_portfolio_task = mock_run_portfolio_task

    if aq is not None and hasattr(aq, "run_analysis"):
        aq.run_analysis = mock_run_analysis

    fas.generate_formula = mock_generate_formula
    prs.get_rebalance_suggestions = mock_get_rebalance_suggestions

    yield

    for (module, name), original_func in originals.items():
        if original_func is not None:
            setattr(module, name, original_func)
        else:
            if hasattr(module, name):
                delattr(module, name)


@pytest.fixture(scope="session", autouse=True)
def cleanup_db_file():
    db_file = "test_e2e_db.sqlite"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass
    yield
    import asyncio

    from backend.core.database import engine

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        import nest_asyncio

        nest_asyncio.apply()
        loop.run_until_complete(engine.dispose())
    else:
        loop.run_until_complete(engine.dispose())

    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass


@pytest_asyncio.fixture(autouse=True)
async def run_app_lifespan():
    from backend.core.log_handler import db_log_handler

    db_log_handler._started = False
    db_log_handler._task = None
    db_log_handler._queue = None
    async with app.router.lifespan_context(app):
        yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def live_prices():
    return LIVE_PRICES


@pytest_asyncio.fixture
async def admin_auth(client):
    response = await client.post("/auth/login", json={"username": "admin", "password": "changeme"})
    assert response.status_code == 200, f"Login failed: {response.text}"
    token_data = response.json()
    token = token_data["access_token"]

    authed_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    authed_client.headers["Authorization"] = f"Bearer {token}"

    yield token, authed_client
    await authed_client.aclose()


@pytest_asyncio.fixture
async def admin_client(admin_auth):
    yield admin_auth[1]


@pytest_asyncio.fixture
async def admin_token(admin_auth):
    yield admin_auth[0]


@pytest_asyncio.fixture
async def user_auth(client):
    from sqlalchemy import select

    from backend.core.security import hash_password
    from backend.models.user import User

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.username == "testuser"))
        existing = res.scalar_one_or_none()
        if not existing:
            hashed = hash_password("testpass")
            db.add(User(username="testuser", hashed_password=hashed, role="user"))
            await db.commit()

    response = await client.post("/auth/login", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 200, f"Login failed: {response.text}"
    token_data = response.json()
    token = token_data["access_token"]

    u_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    u_client.headers["Authorization"] = f"Bearer {token}"
    yield token, u_client
    await u_client.aclose()


@pytest_asyncio.fixture
async def user_client(user_auth):
    yield user_auth[1]
