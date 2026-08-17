import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

import backend.bootstrap  # noqa: F401  (import side-effect: see backend/bootstrap.py)

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

    from backend.trading_agents.agents.runtime.logging_config import setup_unified_logging

    setup_unified_logging()
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    from backend.services.update_service import reset_stuck_update

    reset_stuck_update()

    await create_all_tables()
    await _seed_admin_user()

    try:
        from backend.core.rls_context import BackgroundCapability, trusted_background_session
        from backend.repositories.analysis import cleanup_stale_analyses

        async with trusted_background_session(BackgroundCapability.STARTUP_CLEANUP) as db:
            count = await cleanup_stale_analyses(db)
            if count > 0:
                _logger.info("Marked %d stale analyses as failed.", count)
    except Exception as e:
        _logger.warning("Failed to cleanup stale analyses on startup: %s", e)

    await db_log_handler.start()

    from backend.services.alert_service import check_and_recover_lost_alerts

    try:
        await check_and_recover_lost_alerts()
    except Exception as e:
        _logger.warning("Failed to recover lost alerts: %s", e)

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
    from backend.core.password_hashing import hash_password, is_supported_password_hash
    from backend.models.user import User

    if not settings.ADMIN_USERNAME:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        existing = result.scalar_one_or_none()
        if existing is None:
            raw_hash = settings.ADMIN_PASSWORD_HASH
            if raw_hash and not is_supported_password_hash(raw_hash):
                if settings.ENVIRONMENT.strip().lower() == "production":
                    raise RuntimeError("ADMIN_PASSWORD_HASH is not a valid Argon2 hash")
                _logger.warning(
                    "ADMIN_PASSWORD_HASH in .env is not a valid Argon2 hash; using development fallback."
                )
                raw_hash = None
            if raw_hash:
                hashed = raw_hash
                bootstrap_password = None
            else:
                import secrets

                bootstrap_password = secrets.token_urlsafe(18)
                hashed = hash_password(bootstrap_password)
            db.add(User(username=settings.ADMIN_USERNAME, hashed_password=hashed, role="owner"))
            await db.commit()
            if bootstrap_password:
                # Development-only fallback. Production configuration validation
                # requires an operator-controlled password hash before boot.
                _logger.warning(
                    "Owner user %s created with a one-time development bootstrap password: %s. "
                    "Change it immediately.",
                    settings.ADMIN_USERNAME,
                    bootstrap_password,
                )
            else:
                _logger.info("Owner user created: %s", settings.ADMIN_USERNAME)
        elif existing.role != "owner":
            existing.role = "owner"
            await db.commit()
            _logger.info("Owner role set for existing user: %s", settings.ADMIN_USERNAME)


async def _load_cron_settings(cron):
    try:
        from sqlalchemy import select

        from backend.core.rls_context import BackgroundCapability, trusted_background_session
        from backend.models.settings import AppSettings

        async with trusted_background_session(BackgroundCapability.CRON_BOOTSTRAP) as db:
            app_res = await db.execute(select(AppSettings).where(AppSettings.cron_enabled))
            for app_settings in app_res.scalars():
                await cron.apply_user_settings(app_settings)
    except Exception as e:
        _logger.warning("Could not load cron settings: %s", e)


from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.core.limiter import limiter


def _operation_id(route: APIRoute) -> str:
    """Give each endpoint a short, stable OpenAPI operationId.

    FastAPI's default embeds the full path and method
    (``get_watchlist_api_watchlist_get``), which the generated frontend client
    turns into names like ``useGetWatchlistApiWatchlistGet``. The first tag is
    included because a few handler names (``get_performance``, ``delete_user``,
    ``clear_history``) repeat across routers.
    """
    tag = str(route.tags[0]) if route.tags else "default"
    return f"{tag}_{route.name}"


app = FastAPI(
    title="TradingAgents Web API",
    version="1.0.0",
    description="AI-powered trading dashboard with simulation and live trading support",
    lifespan=lifespan,
    generate_unique_id_function=_operation_id,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from backend.core.body_limit import BodySizeLimitMiddleware
from backend.core.exceptions import register_exception_handlers
from backend.core.security_headers import SecurityHeadersMiddleware

register_exception_handlers(app)
app.add_middleware(
    SecurityHeadersMiddleware,
    production=settings.ENVIRONMENT.strip().lower() == "production",
)
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

_WS_KEEPALIVE_MESSAGE = "__tradingagents_keepalive__"
_WS_AUTH_REVALIDATION_SECONDS = 30.0


async def _reject_websocket(
    websocket: WebSocket,
    *,
    code: int,
    reason: str,
    subprotocol: str | None = None,
) -> None:
    """Send a close frame the browser can diagnose after a rejected handshake.

    Calling ``close`` before ``accept`` turns into an HTTP rejection in most
    ASGI servers, which the browser exposes only as opaque close code 1006.
    Accepting and immediately closing sends a diagnosable close code without
    registering the socket or allowing it to read any task events.
    """
    await websocket.accept(subprotocol=subprotocol)
    await websocket.close(code=code, reason=reason)


async def _analysis_websocket_access_is_current(access_token: str, expected_user_id: int) -> bool:
    """Re-check a connected analysis socket's token and page entitlement.

    This is intentionally a fresh database lookup rather than trusting the
    user object captured at handshake time: logout, password change, account
    deactivation and a revoked analysis page permission must all end an
    already-open stream. Database failures propagate to the caller, which
    closes with 1011 instead of continuing to expose events without a check.
    """
    from backend.api.deps import get_user_from_access_token, has_page_access
    from backend.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            user = await get_user_from_access_token(access_token, db)
        except HTTPException:
            return False
        if user.id != expected_user_id:
            return False
        return await has_page_access(db, user, "analysis")


@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(
    websocket: WebSocket,
    task_id: str,
):
    from backend.api.deps import (
        get_user_from_access_token,
        get_websocket_access_token,
        get_websocket_application_subprotocol,
        has_page_access,
    )
    from backend.core.database import AsyncSessionLocal
    from backend.services.analysis_service import is_task_owner

    offered_subprotocols = websocket.headers.get("sec-websocket-protocol")
    selected_subprotocol = get_websocket_application_subprotocol(offered_subprotocols)
    if selected_subprotocol is None:
        await _reject_websocket(
            websocket,
            code=1002,
            reason="Unsupported WebSocket protocol",
        )
        return

    access_token = get_websocket_access_token(offered_subprotocols)
    if not access_token:
        await _reject_websocket(
            websocket,
            code=4001,
            reason="Unauthorized",
            subprotocol=selected_subprotocol,
        )
        return

    try:
        async with AsyncSessionLocal() as db:
            try:
                user = await get_user_from_access_token(access_token, db)
            except HTTPException:
                await _reject_websocket(
                    websocket,
                    code=4001,
                    reason="Unauthorized",
                    subprotocol=selected_subprotocol,
                )
                return
            page_allowed = await has_page_access(db, user, "analysis")
        if not page_allowed:
            await _reject_websocket(
                websocket,
                code=4003,
                reason="Forbidden",
                subprotocol=selected_subprotocol,
            )
            return
        if not await is_task_owner(task_id, user.id, user.is_admin):
            await _reject_websocket(
                websocket,
                code=4003,
                reason="Forbidden",
                subprotocol=selected_subprotocol,
            )
            return
    except Exception:
        _logger.exception("Analysis WebSocket initialization failed task=%s", task_id)
        try:
            await _reject_websocket(
                websocket,
                code=1011,
                reason="Initialization failed",
                subprotocol=selected_subprotocol,
            )
        except Exception:
            _logger.debug("Could not send WebSocket initialization failure task=%s", task_id, exc_info=True)
        return

    try:
        await ws_manager.connect(task_id, websocket, subprotocol=selected_subprotocol)
        _logger.info(
            "Analysis WebSocket connected task=%s user=%s protocol=%s",
            task_id,
            user.id,
            selected_subprotocol,
        )

        async def _revalidate_or_close() -> bool:
            try:
                is_current = await _analysis_websocket_access_is_current(access_token, user.id)
            except Exception:
                _logger.exception("Analysis WebSocket revalidation failed task=%s user=%s", task_id, user.id)
                await ws_manager.disconnect(task_id, websocket)
                try:
                    await websocket.close(code=1011, reason="Authorization check failed")
                except Exception:
                    _logger.debug("Could not close WebSocket after revalidation error task=%s", task_id, exc_info=True)
                return False
            if is_current:
                return True

            _logger.info("Analysis WebSocket authorization revoked task=%s user=%s", task_id, user.id)
            await ws_manager.disconnect(task_id, websocket)
            try:
                await websocket.close(code=4001, reason="Unauthorized")
            except Exception:
                _logger.debug("Could not close revoked WebSocket task=%s", task_id, exc_info=True)
            return False

        import asyncio

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=_WS_AUTH_REVALIDATION_SECONDS)
            except TimeoutError:
                if not await _revalidate_or_close():
                    return
                continue
            if message == _WS_KEEPALIVE_MESSAGE:
                if not await _revalidate_or_close():
                    return
                continue
    except WebSocketDisconnect as exc:
        await ws_manager.disconnect(task_id, websocket)
        if exc.code not in {1000, 1001}:
            _logger.warning("Analysis WebSocket disconnected abnormally task=%s code=%s", task_id, exc.code)
    except Exception:
        _logger.exception("WebSocket error for task=%s", task_id)
        await ws_manager.disconnect(task_id, websocket)
        try:
            await websocket.close(code=1011, reason="WebSocket error")
        except Exception:
            _logger.debug("Could not close failed WebSocket task=%s", task_id, exc_info=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    _NOT_FOUND_PREFIXES = ("api/", "auth/", "ws/")
    _NOT_FOUND_ROOTS = {"api", "auth", "ws"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path in _NOT_FOUND_ROOTS or full_path.startswith(_NOT_FOUND_PREFIXES):
            raise HTTPException(status_code=404)
        static_root = os.path.realpath(_static_dir)
        candidate = os.path.realpath(os.path.join(static_root, full_path))
        if full_path and os.path.commonpath([static_root, candidate]) == static_root and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
