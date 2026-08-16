"""Token usage analytics and system metrics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_admin, require_page
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.analytics import SystemHealthRead, SystemMetricsRead, TokenUsageRead
from backend.services import system_metrics_service, token_analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/token-usage", response_model=TokenUsageRead)
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("performance")),
) -> TokenUsageRead:
    return TokenUsageRead.model_validate(await token_analytics_service.get_token_analytics(db, current_user.id))


@router.get("/api/admin/system-metrics", response_model=SystemMetricsRead)
async def get_system_metrics(
    _: User = Depends(require_admin),
) -> SystemMetricsRead:
    """Return key Prometheus metrics as JSON for the admin dashboard."""
    return SystemMetricsRead.model_validate(system_metrics_service.collect_system_metrics())


@router.get("/api/admin/system-health", response_model=SystemHealthRead)
async def get_system_health(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SystemHealthRead:
    """Combine guardrail telemetry (Prometheus) and quality history (DB) into one panel."""
    from backend.services.analysis.run_quality import get_recent_quality_summary

    metrics = system_metrics_service.collect_system_metrics()
    return SystemHealthRead(
        signal_parse_fallbacks=metrics.get("signal_parse_fallbacks", 0),
        auto_order_skipped=metrics.get("auto_order_skipped", {}),
        quality=await get_recent_quality_summary(db),
    )
