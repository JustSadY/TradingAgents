from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories import token_analytics as repo

MODEL_COSTS: dict[str, dict[str, tuple[float, float]]] = {
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
    "ollama": {},
}

DEFAULT_COST = (2.0, 8.0)


def estimate_cost(provider: str | None, model: str | None, tokens_in: int, tokens_out: int) -> float:
    prov = (provider or "").lower()
    if prov == "ollama":
        return 0.0
    mod = (model or "").lower()
    rates = MODEL_COSTS.get(prov, {})
    rate_in, rate_out = DEFAULT_COST
    for key, val in rates.items():
        if key in mod:
            rate_in, rate_out = val
            break
    return round((tokens_in * rate_in + tokens_out * rate_out) / 1_000_000, 6)


async def get_token_analytics(db: AsyncSession, user_id: int) -> dict[str, Any]:
    rows = await repo.get_token_usage_rows(db, user_id)
    breakdown: list[dict[str, Any]] = []
    total_in = total_out = total_cost = 0.0
    for row in rows:
        ti = int(row.tokens_in or 0)
        to = int(row.tokens_out or 0)
        cost = estimate_cost(row.llm_provider, row.llm_model, ti, to)
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
