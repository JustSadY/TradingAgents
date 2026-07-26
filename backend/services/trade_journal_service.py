"""Trade Journal service — save/retrieve per-trade notes and generate AI debriefs."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories import portfolio as portfolio_repo
from backend.repositories import trade_note as repo

_logger = logging.getLogger(__name__)


class TradeJournalError(Exception):
    """Raised for client-correctable problems (missing order, missing API key,
    upstream LLM failure) — the API layer translates ``status_code`` into an
    ``HTTPException``, keeping FastAPI/HTTP concerns out of the service."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


async def save_note(db: AsyncSession, user: User, order_id: int, note: str) -> dict:
    """Upsert a user note for an order. Returns {"order_id", "note", "has_debrief"}."""
    # Only allow notes on the user's own orders (orders have no user_id).
    if await portfolio_repo.get_order_by_id(db, order_id, user=user) is None:
        raise TradeJournalError("Order not found.", status_code=404)
    trade_note = await repo.upsert_note(db, order_id=order_id, user_id=user.id, note=note)
    await db.commit()
    return {
        "order_id": order_id,
        "note": trade_note.note,
        "has_debrief": trade_note.ai_debrief is not None,
    }


async def get_note(db: AsyncSession, user: User, order_id: int) -> dict | None:
    """Get note for an order. Returns {"order_id", "note", "ai_debrief", "has_debrief"} or None."""
    trade_note = await repo.get_note(db, order_id=order_id, user_id=user.id)
    if trade_note is None:
        return None
    return {
        "order_id": order_id,
        "note": trade_note.note,
        "ai_debrief": trade_note.ai_debrief,
        "has_debrief": trade_note.ai_debrief is not None,
    }


async def generate_debrief(db: AsyncSession, user: User, order_id: int) -> dict:
    """Generate AI debrief for a trade and persist it."""
    order = await portfolio_repo.get_order_by_id(db, order_id, user=user)
    if order is None:
        raise TradeJournalError("Order not found.", status_code=404)

    trade_note = await repo.get_note(db, order_id=order_id, user_id=user.id)
    note_text = trade_note.note if trade_note else ""

    qty = float(order.quantity_filled or 0)
    price = float(order.price_per_share or 0)
    pnl = float(order.realized_pnl or 0)
    cost_basis = qty * price
    pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0
    reasoning = order.ai_reasoning or ""

    prompt = f"""You are a trading coach. Analyze this completed trade and provide a brief debrief (3-5 sentences):
- Was this trade well-executed?
- What worked or didn't work?
- What would you do differently?
- Rate this trade 1-5 stars.

Trade details:
Ticker: {order.ticker}
Action: {order.action}
Quantity: {qty}
Price: ${price}
Realized P&L: ${pnl} ({pnl_pct:.1f}%)
AI Signal: {order.ai_signal or "N/A"}
AI Reasoning: {reasoning[:500]}
Trader's Note: {note_text or "None provided"}

Give a direct, honest assessment."""

    from langchain_core.messages import HumanMessage

    from backend.core.config import get_settings
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.services.settings_service import get_or_create_settings
    from backend.services.user_service import get_user_api_key
    from backend.trading_agents.llm_clients.factory import create_llm_client

    settings = await get_or_create_settings(db, user)
    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm.get("llm_provider") or settings.llm_provider
    model = pm.get("llm_model") or settings.llm_model

    try:
        user_key = get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception:
        user_key = None

    if not user_key and not user.is_admin:
        raise TradeJournalError(
            f"No API key set for provider '{provider}'. Please add it in Settings.",
            status_code=400,
        )

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (response.content or "").strip()
    except Exception as e:
        _logger.warning("Trade debrief LLM error: %s", e)
        raise TradeJournalError(f"LLM error: {e}", status_code=500) from e

    await repo.set_debrief(db, order_id=order_id, user_id=user.id, debrief=content)
    await db.commit()

    return {"order_id": order_id, "ai_debrief": content}
