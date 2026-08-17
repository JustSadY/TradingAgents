import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
from backend.app.lifespan import lifespan
from backend.core.body_limit import BodySizeLimitMiddleware
from backend.core.config import get_settings
from backend.core.exceptions import register_exception_handlers
from backend.core.limiter import limiter
from backend.core.security_headers import SecurityHeadersMiddleware
from backend.realtime.analysis_websocket import router as analysis_ws_router


def _operation_id(route: APIRoute) -> str:
    """Give each endpoint a short, stable OpenAPI operationId."""
    tag = str(route.tags[0]) if route.tags else "default"
    return f"{tag}_{route.name}"


def _configure_routes(app: FastAPI) -> None:
    for router in (
        auth_router,
        analysis_router,
        watchlist_router,
        portfolio_router,
        settings_router,
        logs_router,
        cron_router,
        trading_router,
        meta_router,
        metrics_router,
        update_router,
        market_router,
        fx_router,
        preset_router,
        alerts_router,
        news_router,
        users_router,
        system_settings_router,
        screener_router,
        sector_rotation_router,
        patterns_router,
        share_router,
        assistant_router,
        daily_summary_router,
        token_analytics_router,
        earnings_router,
        correlation_router,
        personas_api_router,
        analysis_ws_router,
    ):
        app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}


def _configure_static_files(app: FastAPI) -> None:
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    static_dir = os.path.realpath(static_dir)
    if not os.path.isdir(static_dir):
        return

    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    not_found_prefixes = ("api/", "auth/", "ws/")
    not_found_roots = {"api", "auth", "ws"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path in not_found_roots or full_path.startswith(not_found_prefixes):
            raise HTTPException(status_code=404)
        candidate = os.path.realpath(os.path.join(static_dir, full_path))
        if full_path and os.path.commonpath([static_dir, candidate]) == static_dir and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(static_dir, "index.html"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TradingAgents Web API",
        version="1.0.0",
        description="AI-powered trading dashboard with simulation and live trading support",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

    _configure_routes(app)
    _configure_static_files(app)
    return app
