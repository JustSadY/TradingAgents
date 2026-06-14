"""Token usage analytics and system metrics endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.core.database import get_db
from backend.models.analysis import AnalysisResult
from backend.models.user import User

router = APIRouter(tags=["analytics"])

# Approximate cost per 1M tokens (input_usd, output_usd)
_MODEL_COSTS: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (5.0, 15.0),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o1": (15.0, 60.0),
        "o1-mini": (3.0, 12.0),
        "o3-mini": (1.10, 4.40),
        "o4-mini": (1.10, 4.40),
    },
    "anthropic": {
        "claude-3-5-sonnet": (3.0, 15.0),
        "claude-3-5-haiku": (0.80, 4.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-sonnet-4": (3.0, 15.0),
        "claude-haiku-4": (0.80, 4.0),
        "claude-opus-4": (15.0, 75.0),
    },
    "google": {
        "gemini-1.5-pro": (3.50, 10.50),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-2.0-flash": (0.075, 0.30),
        "gemini-2.5-pro": (7.0, 21.0),
        "gemini-2.5-flash": (0.15, 0.60),
    },
    "nvidia": {
        "llama-3.1-70b": (0.35, 0.35),
        "llama-3.1-405b": (2.00, 2.00),
        "llama-3.3-70b": (0.35, 0.35),
    },
    "ollama": {},  # local inference — $0 cost
}

_DEFAULT_COST = (2.0, 8.0)


def _estimate_cost(provider: str | None, model: str | None, tokens_in: int, tokens_out: int) -> float:
    prov = (provider or "").lower()
    if prov == "ollama":
        return 0.0
    mod = (model or "").lower()
    rates = _MODEL_COSTS.get(prov, {})
    rate_in, rate_out = _DEFAULT_COST
    for key, val in rates.items():
        if key in mod:
            rate_in, rate_out = val
            break
    return round((tokens_in * rate_in + tokens_out * rate_out) / 1_000_000, 6)


@router.get("/api/analytics/token-usage")
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    q = (
        select(
            AnalysisResult.llm_provider,
            AnalysisResult.llm_model,
            func.coalesce(func.sum(AnalysisResult.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AnalysisResult.tokens_out), 0).label("tokens_out"),
            func.count(AnalysisResult.id).label("analyses"),
        )
        .where(
            AnalysisResult.user_id == current_user.id,
            AnalysisResult.status == "completed",
        )
        .group_by(AnalysisResult.llm_provider, AnalysisResult.llm_model)
    )
    rows = (await db.execute(q)).all()

    breakdown: list[dict[str, Any]] = []
    total_in = total_out = total_cost = 0.0
    for row in rows:
        ti = int(row.tokens_in or 0)
        to = int(row.tokens_out or 0)
        cost = _estimate_cost(row.llm_provider, row.llm_model, ti, to)
        breakdown.append(
            {
                "provider": row.llm_provider or "unknown",
                "model": row.llm_model or "unknown",
                "tokens_in": ti,
                "tokens_out": to,
                "analyses": int(row.analyses),
                "estimated_cost_usd": cost,
            }
        )
        total_in += ti
        total_out += to
        total_cost += cost

    daily_q = (
        select(
            func.date(AnalysisResult.created_at).label("day"),
            func.coalesce(func.sum(AnalysisResult.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AnalysisResult.tokens_out), 0).label("tokens_out"),
            func.count(AnalysisResult.id).label("analyses"),
        )
        .where(
            AnalysisResult.user_id == current_user.id,
            AnalysisResult.status == "completed",
        )
        .group_by(func.date(AnalysisResult.created_at))
        .order_by(func.date(AnalysisResult.created_at))
        .limit(30)
    )
    daily_rows = (await db.execute(daily_q)).all()
    daily = [
        {
            "day": str(row.day),
            "tokens_in": int(row.tokens_in or 0),
            "tokens_out": int(row.tokens_out or 0),
            "analyses": int(row.analyses),
        }
        for row in daily_rows
    ]

    return {
        "total_tokens_in": int(total_in),
        "total_tokens_out": int(total_out),
        "total_tokens": int(total_in + total_out),
        "total_cost_usd": round(total_cost, 4),
        "breakdown": sorted(breakdown, key=lambda x: x["estimated_cost_usd"], reverse=True),
        "daily": daily,
    }


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
