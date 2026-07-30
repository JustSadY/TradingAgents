"""
Main Agent: Portfolio Manager (root / final decision maker).

Synthesises the risk debate and the research + trade plans into the final
trade decision. As the root of the tree, disabling it is the global kill-switch
— the whole run collapses to an automated Hold.

Kill-switch behaviour:
  • portfolio_manager disabled  → emit an automated Hold decision and run
    nothing. (Because every other branch is a descendant of this root, the
    hierarchy's cascade also disables them, so the upstream main nodes will
    already have short-circuited.)
"""

from __future__ import annotations

import inspect
import logging

from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.sub.managers.portfolio_manager import create_portfolio_manager

logger = logging.getLogger(__name__)

MAIN_KEY = "portfolio_manager"

_HOLD = "Hold — automated fallback: Portfolio Manager disabled or unavailable."


def create_portfolio_manager_node(ctx: AgentRunContext) -> NodeFn:
    async def portfolio_manager_node(state) -> dict:
        if not ctx.is_branch_enabled(MAIN_KEY):
            logger.info("[portfolio_manager] disabled — emitting automated Hold.")
            return {"final_trade_decision": _HOLD, "final_signal": "Hold"}

        run = create_portfolio_manager(ctx.llm_for("portfolio_manager"))
        try:
            if inspect.iscoroutinefunction(run):
                return await run(state)
            return run(state)
        except Exception as exc:
            logger.warning("[portfolio_manager] failed: %s — emitting Hold.", exc)
            return {"final_trade_decision": _HOLD, "final_signal": "Hold"}

    return portfolio_manager_node
