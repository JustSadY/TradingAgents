"""Token usage analytics and system metrics endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_admin, require_page
from backend.core.database import get_db
from backend.models.user import User
from backend.services import system_metrics_service, token_analytics_service

router = APIRouter(tags=["analytics"])

@router.get("/api/analytics/token-usage", response_model=dict[str, Any])
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("performance")),
) -> dict[str, Any]:
    return await token_analytics_service.get_token_analytics(db, current_user.id)

@router.get("/api/admin/system-metrics", response_model=dict[str, Any])
async def get_system_metrics(
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Return key Prometheus metrics as JSON for the admin dashboard."""
    return system_metrics_service.collect_system_metrics()

@router.get("/api/admin/system-health", response_model=dict[str, Any])
async def get_system_health(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Combine guardrail telemetry (Prometheus) and quality history (DB) into one panel."""
    from backend.services.analysis.run_quality import get_recent_quality_summary

    metrics = system_metrics_service.collect_system_metrics()
    quality = await get_recent_quality_summary(db)
    return {
        "signal_parse_fallbacks": metrics.get("signal_parse_fallbacks", 0),
        "auto_order_skipped": metrics.get("auto_order_skipped", {}),
        "quality": quality,
    }
