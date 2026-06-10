# Bootstrap must run before any import that transitively pulls in the
# backend.trading_agents engine (sets engine env defaults + logging stub).
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import backend.bootstrap  # noqa: F401  (import side-effect: see backend/bootstrap.py)
from backend.api.alerts import router as alerts_router
from backend.api.analysis import router as analysis_router
from backend.api.auth import router as auth_router
from backend.api.cron import router as cron_router
from backend.api.logs import router as logs_router
from backend.api.market import router as market_router
from backend.api.meta import router as meta_router
from backend.api.news import router as news_router
from backend.api.portfolio import router as portfolio_router
from backend.api.preset import router as preset_router
from backend.api.screener import router as screener_router
from backend.api.settings import router as settings_router
from backend.api.system_settings import router as system_settings_router
from backend.api.trading import router as trading_router
from backend.api.update import router as update_router
from backend.api.users import router as users_router
from backend.api.watchlist import router as watchlist_router
from backend.core.config import get_settings
from backend.core.database import create_all_tables
from backend.core.security import decode_token
from backend.core.websocket import ws_manager
from backend.services.cron_service import init_cron_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)
settings = get_settings()
from backend.core.log_handler import db_log_handler
from backend.core.log_redaction import install_redaction

install_redaction(*logging.getLogger().handlers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("Starting TradingAgents Web API...")
    
    # Register all tools during startup
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    
    await create_all_tables()
    await _seed_admin_user()

    # PERSISTENCE: Cleanup analyses that were interrupted by a crash/restart
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.analysis import cleanup_stale_analyses

        async with AsyncSessionLocal() as db:
            count = await cleanup_stale_analyses(db)
            if count > 0:
                _logger.info("Marked %d stale analyses as failed.", count)
    except Exception as e:
        _logger.warning("Failed to cleanup stale analyses on startup: %s", e)

    await db_log_handler.start()

    # Recover any lost alert analyses from crash/abrupt shutdown
    from backend.services.alert_service import check_and_recover_lost_alerts

    try:
        await check_and_recover_lost_alerts()
    except Exception as e:
        _logger.warning("Failed to recover lost alerts: %s", e)

    cron = init_cron_service()
    await _load_cron_settings(cron)
    cron.start()
    _logger.info("Application ready.")
    yield
    cron.stop()

    # Gracefully await any running analyses or alert tasks on shutdown
    import asyncio

    from backend.services.alert_service import _BACKGROUND_TASKS
    from backend.services.analysis_service import _RUNNING_TASKS

    pending = list(_RUNNING_TASKS.values()) + list(_BACKGROUND_TASKS)
    if pending:
        _logger.info("Waiting for %d running background analysis/alert tasks...", len(pending))
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=15.0)
        except TimeoutError:
            _logger.warning("Timeout waiting for background tasks to complete during shutdown.")

    _logger.info("Application stopped.")
    db_log_handler.stop()


async def _seed_admin_user():
    from sqlalchemy import select

    from backend.core.database import AsyncSessionLocal
    from backend.core.security import hash_password
    from backend.models.user import User

    if not settings.ADMIN_USERNAME:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        existing = result.scalar_one_or_none()
        if existing is None:
            hashed = settings.ADMIN_PASSWORD_HASH or hash_password("changeme")
            db.add(User(username=settings.ADMIN_USERNAME, hashed_password=hashed, role="owner"))
            await db.commit()
            _logger.info("Owner user created: %s", settings.ADMIN_USERNAME)
        elif existing.role != "owner":
            existing.role = "owner"
            await db.commit()
            _logger.info("Owner role set for existing user: %s", settings.ADMIN_USERNAME)


async def _load_cron_settings(cron):
    try:
        from sqlalchemy import select

        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import AppSettings

        async with AsyncSessionLocal() as db:
            app_res = await db.execute(select(AppSettings).where(AppSettings.cron_enabled == True))
            for app_settings in app_res.scalars():
                await cron.apply_user_settings(app_settings)
    except Exception as e:
        _logger.warning("Could not load cron settings: %s", e)


from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.core.limiter import limiter

app = FastAPI(
    title="TradingAgents Web API",
    version="1.0.0",
    description="AI-powered trading dashboard with simulation and live trading support",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from backend.core.exceptions import register_exception_handlers

register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(settings_router)
app.include_router(logs_router)
app.include_router(cron_router)
app.include_router(trading_router)
app.include_router(meta_router)
app.include_router(update_router)
app.include_router(market_router)
app.include_router(preset_router)
app.include_router(alerts_router)
app.include_router(news_router)
app.include_router(users_router)
app.include_router(system_settings_router)
app.include_router(screener_router)


@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(..., description="JWT access token"),
):
    try:
        username = decode_token(token, expected_type="access")
    except ValueError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    from backend.core.database import AsyncSessionLocal
    from backend.repositories.users import get_user_by_username
    from backend.services.analysis_service import is_task_owner

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    # Only the user who started the run (or an admin) may stream its events;
    # otherwise any authenticated user could read another user's analysis.
    if not is_task_owner(task_id, user.id, user.is_admin):
        await websocket.close(code=4003, reason="Forbidden")
        return

    await ws_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}


_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
