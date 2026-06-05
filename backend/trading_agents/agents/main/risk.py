"""
Main Agent: Risk Debate.

Owns the three risk sub-agents (aggressive, conservative, neutral). Runs their
debate imperatively, replicating the old
``ConditionalLogic.should_continue_risk_analysis`` rotation
(Aggressive → Conservative → Neutral → …, stop at ``3 × max_risk_discuss_rounds``).
The final decision itself is made downstream by the Portfolio Manager from the
accumulated debate history.

Kill-switch behaviour:
  • risk_debate disabled    → emit a neutral debate state and skip every sub.
  • a single risk sub off   → that speaker is dropped from the rotation.
"""
from __future__ import annotations

import logging
import inspect

from backend.trading_agents.agents.base import (
    AgentRunContext, NodeFn, neutral_risk_debate_state,
)
from backend.trading_agents.agents.sub.risk_mgmt.aggressive_debator import create_aggressive_debator
from backend.trading_agents.agents.sub.risk_mgmt.conservative_debator import create_conservative_debator
from backend.trading_agents.agents.sub.risk_mgmt.neutral_debator import create_neutral_debator

logger = logging.getLogger(__name__)

MAIN_KEY = "risk_debate"


def create_risk_debate_node(ctx: AgentRunContext) -> NodeFn:
    async def risk_debate_node(state) -> dict:
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[risk_debate] branch disabled — skipping risk debate.")
            return {"risk_debate_state": neutral_risk_debate_state(
                "Risk debate disabled by configuration."
            )}

        llm = ctx.llm_for("risk_debate")
        # Speaker rotation in canonical order, filtered by per-sub enable.
        # All three share the "risk_debate" enable/LLM in the catalog, but we
        # still honour an explicit per-key override if one exists.
        rotation = [
            ("aggressive", create_aggressive_debator(llm)),
            ("conservative", create_conservative_debator(llm)),
            ("neutral", create_neutral_debator(llm)),
        ]
        rotation = [(name, fn) for name, fn in rotation if ctx.is_enabled("risk_debate")]
        if not rotation:
            return {"risk_debate_state": neutral_risk_debate_state()}

        local = dict(state)
        if not local.get("risk_debate_state"):
            local["risk_debate_state"] = neutral_risk_debate_state()

        max_rounds = ctx.config.get("max_risk_discuss_rounds", 1)
        total_turns = 3 * max_rounds
        out: dict = {}
        idx = 0
        guard = 0
        while local["risk_debate_state"]["count"] < total_turns and guard < 60:
            guard += 1
            name, fn = rotation[idx % len(rotation)]
            idx += 1
            try:
                if inspect.iscoroutinefunction(fn):
                    upd = await fn(local)
                else:
                    upd = fn(local)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[risk_debate] '%s' failed: %s — counting a skip.", name, exc)
                rs = dict(local["risk_debate_state"])
                rs["count"] = int(rs.get("count", 0)) + 1
                rs["latest_speaker"] = name.title()
                upd = {"risk_debate_state": rs}
            out.update(upd)
            local.update(upd)

        return out

    return risk_debate_node
