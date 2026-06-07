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

The three debators are not individually registered in the catalog; they share
the single ``risk_debate`` enable, so the whole trio runs (or none of it does).
"""

from __future__ import annotations

import inspect
import logging

from backend.trading_agents.agents.base import (
    AgentRunContext,
    NodeFn,
    neutral_risk_debate_state,
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
            return {"risk_debate_state": neutral_risk_debate_state("Risk debate disabled by configuration.")}

        llm = ctx.llm_for("risk_debate")
        # The three debators are not separately registered in the agent catalog
        # — they share the single "risk_debate" enable/LLM (already checked
        # above), so the whole trio runs in canonical order whenever risk debate
        # is enabled. (A previous per-speaker filter here keyed off the constant
        # "risk_debate" and so was a no-op.)
        rotation = [
            ("aggressive", create_aggressive_debator(llm)),
            ("conservative", create_conservative_debator(llm)),
            ("neutral", create_neutral_debator(llm)),
        ]

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
