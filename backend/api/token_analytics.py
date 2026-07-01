"""Token usage analytics and system metrics endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.core.database import get_db
from backend.models.user import User
from backend.services import system_metrics_service, token_analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/token-usage")
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await token_analytics_service.get_token_analytics(db, current_user.id)


@router.get("/api/admin/system-metrics")
async def get_system_metrics(
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Return key Prometheus metrics as JSON for the admin dashboard."""
    return system_metrics_service.collect_system_metrics()
