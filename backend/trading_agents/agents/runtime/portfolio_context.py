"""Auto-pulled portfolio context for the decision agents.

Agents used to be prompted with manually-entered account values (or hardcoded
ones like a "$100,000 portfolio"). This pulls the user's actual simulation
portfolio — cash and current holdings — from the database so the trader,
portfolio manager and super portfolio manager size positions against the real
account state. Returns "" when there is no portfolio or on any error (the agents
must still run).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def get_portfolio_context(user_id: int | None) -> str:
    if not user_id:
        return ""
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.portfolio import get_simulation_portfolio

        async with AsyncSessionLocal() as db:
            portfolio = await get_simulation_portfolio(db, user_id=user_id)
            if not portfolio:
                return ""

            cash = float(portfolio.cash_available)
            lines = [
                "=== YOUR CURRENT PORTFOLIO (auto-pulled from the system) ===",
                f"- Cash available to deploy: ${cash:,.2f}",
            ]

            holdings = list(portfolio.holdings or [])
            invested = 0.0
            if holdings:
                lines.append("- Current holdings:")
                for h in holdings:
                    qty = float(h.quantity)
                    price = float(h.current_price or 0)
                    avg = float(h.avg_buy_price or 0)
                    value = qty * price
                    invested += value
                    pnl_pct = ((price - avg) / avg * 100) if avg else 0.0
                    lines.append(
                        f"  • {h.ticker}: {qty:g} @ ${price:,.2f} = ${value:,.2f} "
                        f"(avg cost ${avg:,.2f}, {pnl_pct:+.1f}%)"
                    )
            else:
                lines.append("- Current holdings: none (fully in cash)")

            lines.append(f"- Total portfolio value: ${cash + invested:,.2f}")
            lines.append("Size positions against these real figures; do not assume a different balance.")
            return "\n".join(lines)
    except Exception as exc:
        logger.warning("Could not fetch portfolio context for user_id=%s: %s", user_id, exc)
        return ""
