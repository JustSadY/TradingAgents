"""Deprecated compatibility shim for the retired Trader graph stage.

The active graph is ``Research Manager -> Risk Debate -> Portfolio Manager``.
This factory remains import-compatible for extensions compiled against older
versions, but it cannot call an LLM or produce a competing order proposal.
"""

from __future__ import annotations

from backend.trading_agents.agents.base import AgentRunContext, NodeFn


def create_trader_node(_ctx: AgentRunContext) -> NodeFn:
    async def trader_node(_state) -> dict:
        return {
            "trader_investment_plan": "",
            "trader_proposal_json": "{}",
        }

    return trader_node
