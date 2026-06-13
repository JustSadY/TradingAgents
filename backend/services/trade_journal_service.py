"""Trade Journal service — save/retrieve per-trade notes and generate AI debriefs."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.user import User
from backend.repositories import trade_note as repo

_logger = logging.getLogger(__name__)


async def save_note(db: AsyncSession, user: User, order_id: int, note: str) -> dict:
    """Upsert a user note for an order. Returns {"order_id", "note", "has_debrief"}."""
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
    # 1. Fetch the order (scoped to user via portfolio)
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")

    # 2. Fetch the note (may be empty string)
    trade_note = await repo.get_note(db, order_id=order_id, user_id=user.id)
    note_text = trade_note.note if trade_note else ""

    # 3. Build prompt
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

    # 4. Call LLM
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
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{provider}'. Please add it in Settings.",
        )

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (response.content or "").strip()
    except Exception as e:
        _logger.warning("Trade debrief LLM error: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM error: {e}") from e

    # 5. Save the debrief
    await repo.set_debrief(db, order_id=order_id, user_id=user.id, debrief=content)
    await db.commit()

    # 6. Return result
    return {"order_id": order_id, "ai_debrief": content}
