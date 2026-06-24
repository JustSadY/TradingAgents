"""Token usage analytics and system metrics endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.core.database import get_db
from backend.models.user import User
from backend.services import token_analytics_service

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
    try:
        from prometheus_client import REGISTRY
    except ImportError:
        return {"error": "prometheus_client not available"}

    result: dict[str, Any] = {
        "analysis_runs": {},
        "analysis_duration": {"count": 0, "sum_seconds": 0.0, "avg_seconds": 0.0},
        "node_errors": {},
        "node_fallbacks": {},
        "node_retries": 0,
        "websocket_connections": 0,
    }

    for metric in REGISTRY.collect():
        name = metric.name
        if name == "tradingagents_analysis_runs_total":
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    status = sample.labels.get("status", "unknown")
                    result["analysis_runs"][status] = int(sample.value)
        elif name == "tradingagents_analysis_duration_seconds":
            for sample in metric.samples:
                if sample.name.endswith("_count"):
                    result["analysis_duration"]["count"] = int(sample.value)
                elif sample.name.endswith("_sum"):
                    result["analysis_duration"]["sum_seconds"] = round(sample.value, 2)
        elif name == "tradingagents_node_errors_total":
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    node = sample.labels.get("node", "unknown")
                    result["node_errors"][node] = result["node_errors"].get(node, 0) + int(sample.value)
        elif name == "tradingagents_node_fallbacks_total":
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    node = sample.labels.get("node", "unknown")
                    result["node_fallbacks"][node] = result["node_fallbacks"].get(node, 0) + int(sample.value)
        elif name == "tradingagents_node_retries_total":
            result["node_retries"] = sum(int(s.value) for s in metric.samples if s.name.endswith("_total"))
        elif name == "tradingagents_websocket_connections":
            for sample in metric.samples:
                result["websocket_connections"] = int(sample.value)

    total_runs = sum(result["analysis_runs"].values())
    result["total_runs"] = total_runs
    dur = result["analysis_duration"]
    if dur["count"] > 0:
        dur["avg_seconds"] = round(dur["sum_seconds"] / dur["count"], 1)

    total_errors = sum(result["node_errors"].values())
    result["error_rate_pct"] = round(total_errors / total_runs * 100, 1) if total_runs else 0.0

    return result
