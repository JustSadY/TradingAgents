from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.model_pricing import estimate_token_cost, resolve_model_pricing
from backend.repositories import token_analytics as repo


def estimate_cost(provider: str | None, model: str | None, tokens_in: int, tokens_out: int) -> float:
    """Estimate from the canonical pricing catalogue.

    Keep this small wrapper for existing callers while the actual model price
    resolution lives in ``backend.core.model_pricing``.
    """
    return estimate_token_cost(provider, model, tokens_in, tokens_out)


async def get_token_analytics(db: AsyncSession, user_id: int) -> dict[str, Any]:
    rows = await repo.get_token_usage_rows(db, user_id)
    breakdown: list[dict[str, Any]] = []
    total_in = total_out = total_cost = 0.0
    for row in rows:
        ti = int(row.tokens_in or 0)
        to = int(row.tokens_out or 0)
        pricing = resolve_model_pricing(row.llm_provider, row.llm_model)
        cost = estimate_cost(row.llm_provider, row.llm_model, ti, to)
        breakdown.append(
            {
                "provider": row.llm_provider or "unknown",
                "model": row.llm_model or "unknown",
                "tokens_in": ti,
                "tokens_out": to,
                "analyses": int(row.analyses),
                "estimated_cost_usd": cost,
                "pricing_source": pricing.source,
                "pricing_is_fallback": pricing.is_fallback,
            }
        )
        total_in += ti
        total_out += to
        total_cost += cost

    daily_rows = await repo.get_daily_token_usage_rows(db, user_id, 30)
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
