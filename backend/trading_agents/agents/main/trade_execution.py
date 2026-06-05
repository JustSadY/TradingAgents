"""
Main Agent: Trader.

Owns the single execution-planner sub-agent, which turns the research plan into
a concrete trade proposal (entry / stop / target / confidence).

Kill-switch behaviour:
  • trader disabled  → emit a neutral plan and skip the sub-agent (zero tokens).
"""
from __future__ import annotations

import logging
import inspect

from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.sub.trader.trader import create_trader

logger = logging.getLogger(__name__)

MAIN_KEY = "trader"


def create_trader_node(ctx: AgentRunContext) -> NodeFn:
    async def trader_node(state) -> dict:
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[trader] branch disabled — skipping trade planning.")
            return {
                "trader_investment_plan": "Trader disabled by configuration; deferring to risk debate.",
                "trader_proposal_json": "{}",
            }

        run = create_trader(ctx.llm_for("trader"))
        try:
            if inspect.iscoroutinefunction(run):
                return await run(state)
            return run(state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[trader] sub-agent failed: %s — using fallback.", exc)
            return {
                "trader_investment_plan": "Trader agent unavailable; deferring to risk debate.",
                "trader_proposal_json": "{}",
            }

    return trader_node
