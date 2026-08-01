"""Deprecated compatibility shim for the removed Trader LLM.

Historically this module asked a second model to generate a Buy/Sell direction
and position size before the Portfolio Manager made another decision. That
created contradictory order recommendations. New graph runs never call this
factory; keeping a no-op factory avoids breaking third-party imports while
guaranteeing it cannot create an executable competing plan.
"""

from __future__ import annotations

import functools


def create_trader(_llm):
    """Return a legacy no-op node; final execution belongs to Portfolio Manager."""

    async def trader_node(_state, name: str) -> dict:
        return {
            "trader_investment_plan": "",
            "trader_proposal_json": "{}",
            "sender": name,
        }

    return functools.partial(trader_node, name="Legacy Trader")
