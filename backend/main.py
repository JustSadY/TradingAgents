# Bootstrap must run before any import that transitively pulls in the
# backend.trading_agents engine (sets engine env defaults + logging stub).
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import backend.bootstrap  # noqa: F401  (import side-effect: see backend/bootstrap.py)

# Console logging must be configured BEFORE the router imports below: they
# transitively import the backend.trading_agents engine, whose logging setup
# only preserves console output that already exists (see
# agents/runtime/logging_config.py). Configuring it later leaves the app
# without console/journalctl logs.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from backend.api.alerts import router as alerts_router
from backend.api.analysis import router as analysis_router
from backend.api.assistant import router as assistant_router
from backend.api.auth import router as auth_router
from backend.api.correlation import router as correlation_router
from backend.api.cron import router as cron_router
from backend.api.daily_summary import router as daily_summary_router
from backend.api.earnings import router as earnings_router
from backend.api.fx import router as fx_router
from backend.api.logs import router as logs_router
from backend.api.market import router as market_router
from backend.api.meta import router as meta_router
from backend.api.metrics import router as metrics_router
from backend.api.news import router as news_router
from backend.api.patterns import router as patterns_router
from backend.api.personas_api import router as personas_api_router
from backend.api.portfolio import router as portfolio_router
from backend.api.preset import router as preset_router
from backend.api.screener import router as screener_router
from backend.api.sector_rotation import router as sector_rotation_router
from backend.api.settings import router as settings_router
from backend.api.share import router as share_router
from backend.api.system_settings import router as system_settings_router
from backend.api.token_analytics import router as token_analytics_router
from backend.api.trading import router as trading_router
from backend.api.update import router as update_router
from backend.api.users import router as users_router
from backend.api.watchlist import router as watchlist_router
from backend.core.config import get_settings
from backend.core.database import create_all_tables
from backend.core.security import decode_token_payload
from backend.core.websocket import ws_manager
from backend.services.cron_service import init_cron_service

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
    from backend.services.update_service import reset_stuck_update

    reset_stuck_update()

    await create_all_tables()
    await _seed_admin_user()
    await _seed_setting_permissions()
    await _migrate_analysis_subpage_permissions()

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

    # With Redis enabled, forward pub/sub analysis events to local WebSockets
    # and listen for cross-process cancel requests (arq worker mode).
    redis_tasks: list = []
    from backend.core.redis_bus import redis_enabled

    if redis_enabled():
        import asyncio as _asyncio

        from backend.core.event_bus import event_forwarder
        from backend.core.task_store import control_listener
        from backend.services.analysis_service import cancel_local_task

        redis_tasks.append(_asyncio.create_task(event_forwarder()))
        redis_tasks.append(_asyncio.create_task(control_listener(cancel_local_task)))
        _logger.info("Redis event bus active (queue mode: %s).", settings.ANALYSIS_QUEUE_MODE)

    cron = init_cron_service()
    await _load_cron_settings(cron)
    cron.start()
    _logger.info("Application ready.")
    yield
    cron.stop()

    for task in redis_tasks:
        task.cancel()

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

    from backend.core.redis_bus import close_redis
    from backend.services.analysis_queue import close_arq_pool

    await close_arq_pool()
    await close_redis()

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
            raw_hash = settings.ADMIN_PASSWORD_HASH
            if raw_hash:
                try:
                    import bcrypt

                    bcrypt.checkpw(b"test", raw_hash.encode())
                except Exception:
                    _logger.warning("ADMIN_PASSWORD_HASH in .env is not a valid bcrypt hash; using fallback.")
                    raw_hash = None
            hashed = raw_hash or hash_password("changeme")
            db.add(User(username=settings.ADMIN_USERNAME, hashed_password=hashed, role="owner"))
            await db.commit()
            _logger.info("Owner user created: %s", settings.ADMIN_USERNAME)
        elif existing.role != "owner":
            existing.role = "owner"
            await db.commit()
            _logger.info("Owner role set for existing user: %s", settings.ADMIN_USERNAME)


async def _seed_setting_permissions():
    from sqlalchemy import select

    from backend.core.constants import SETTING_KEYS
    from backend.core.database import AsyncSessionLocal
    from backend.models.page_permission import UserSettingPermission
    from backend.models.user import User

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        for u in users:
            for s_key in SETTING_KEYS:
                exists_res = await db.execute(
                    select(UserSettingPermission)
                    .where(UserSettingPermission.user_id == u.id)
                    .where(UserSettingPermission.setting_key == s_key)
                )
                existing = exists_res.scalar_one_or_none()
                if not existing:
                    db.add(UserSettingPermission(user_id=u.id, setting_key=s_key, allowed=True))
        await db.commit()


async def _migrate_analysis_subpage_permissions():
    """One-time backfill for the "screener"/"sector-rotation"/"earnings" page
    keys added after they used to piggyback on the "analysis" permission.

    Without this, every existing non-admin user who could already reach these
    pages via "analysis" access would silently lose them the moment this
    version deploys, until an admin re-granted each one individually. Grant a
    page only when the user already has "analysis" allowed and has no
    explicit row yet for the new key — never override an admin's own choice.
    """
    from sqlalchemy import select

    from backend.core.database import AsyncSessionLocal
    from backend.models.page_permission import UserPagePermission
    from backend.models.user import User

    new_keys = ("screener", "sector-rotation", "earnings")
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        for u in users:
            analysis_res = await db.execute(
                select(UserPagePermission)
                .where(UserPagePermission.user_id == u.id)
                .where(UserPagePermission.page_key == "analysis")
            )
            analysis_perm = analysis_res.scalar_one_or_none()
            if not analysis_perm or not analysis_perm.allowed:
                continue
            for key in new_keys:
                exists_res = await db.execute(
                    select(UserPagePermission)
                    .where(UserPagePermission.user_id == u.id)
                    .where(UserPagePermission.page_key == key)
                )
                if not exists_res.scalar_one_or_none():
                    db.add(UserPagePermission(user_id=u.id, page_key=key, allowed=True))
        await db.commit()


async def _load_cron_settings(cron):
    try:
        from sqlalchemy import select

        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import AppSettings

        async with AsyncSessionLocal() as db:
            app_res = await db.execute(select(AppSettings).where(AppSettings.cron_enabled))
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

from backend.core.body_limit import BodySizeLimitMiddleware
from backend.core.exceptions import register_exception_handlers

register_exception_handlers(app)
app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.MAX_REQUEST_BODY_BYTES)
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
app.include_router(metrics_router)
app.include_router(update_router)
app.include_router(market_router)
app.include_router(fx_router)
app.include_router(preset_router)
app.include_router(alerts_router)
app.include_router(news_router)
app.include_router(users_router)
app.include_router(system_settings_router)
app.include_router(screener_router)
app.include_router(sector_rotation_router)
app.include_router(patterns_router)
app.include_router(share_router)
app.include_router(assistant_router)
app.include_router(daily_summary_router)
app.include_router(token_analytics_router)
app.include_router(earnings_router)
app.include_router(correlation_router)
app.include_router(personas_api_router)


@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(..., description="JWT access token"),
):
    try:
        payload = decode_token_payload(token, expected_type="access")
    except ValueError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    from backend.core.database import AsyncSessionLocal
    from backend.repositories.users import get_user_by_username
    from backend.services.analysis_service import is_task_owner

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, payload["sub"])
    if user is None or not user.is_active:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    # Reject tokens minted before the user's current version, mirroring
    # get_current_user — otherwise a logged-out access token keeps streaming
    # analysis events until it naturally expires.
    if payload.get("ver", 0) != getattr(user, "token_version", 0):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    # Only the user who started the run (or an admin) may stream its events;
    # otherwise any authenticated user could read another user's analysis.
    if not await is_task_owner(task_id, user.id, user.is_admin):
        await websocket.close(code=4003, reason="Forbidden")
        return

    await ws_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(task_id, websocket)
    except Exception:
        _logger.exception("WebSocket error for task=%s", task_id)
        await ws_manager.disconnect(task_id, websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}


_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    # Paths under these prefixes are always backend routes. If none of the
    # routers above matched, the request is a genuinely unknown/misspelled
    # endpoint — it must 404, not silently fall through to index.html (which
    # previously masked bugs like a frontend calling the wrong API path).
    _NOT_FOUND_PREFIXES = ("api/", "auth/", "ws/")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith(_NOT_FOUND_PREFIXES):
            raise HTTPException(status_code=404)
        # Serve real static files (manifest.json, favicon.svg, icons.svg, ...)
        # literally instead of masking them with the SPA shell. Resolve and
        # confirm the path stays inside _static_dir first — full_path is
        # attacker-controlled and must not be able to escape via "..".
        static_root = os.path.realpath(_static_dir)
        candidate = os.path.realpath(os.path.join(static_root, full_path))
        if (
            full_path
            and os.path.commonpath([static_root, candidate]) == static_root
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
