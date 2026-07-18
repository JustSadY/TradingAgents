"""
Main Agent: Risk Debate.

Previously ran three separate LLM calls (one per stance). Merged into a single
call that produces all three perspectives at once, reducing quota consumption
from 3→1 per analysis round.

Kill-switch behaviour:
  • risk_debate disabled    → emit a neutral debate state and skip every sub.
"""

from __future__ import annotations

import logging
import re

from backend.trading_agents.agents.base import (
    AgentRunContext,
    NodeFn,
    neutral_risk_debate_state,
)

logger = logging.getLogger(__name__)

MAIN_KEY = "risk_debate"


def _build_merged_prompt(trader_decision: str, resources_text: str) -> str:
    return f"""You are the Risk Debate Panel consisting of three analysts evaluating the trader's proposal.

TRADER'S INVESTMENT PLAN:
{trader_decision}

MARKET DATA & ANALYSIS:
{resources_text}

INSTRUCTIONS:
Provide all three risk perspectives in sequence using the exact format below.

**Aggressive Risk Analyst** — Champion the high-reward aspects. Emphasize upside potential, competitive advantages, and why bold action is warranted even with elevated risk.

**Conservative Risk Analyst** — Prioritize capital preservation. Highlight downside risks, worst-case scenarios, and logical flaws in aggressive optimism.

**Neutral Risk Analyst** — Provide a balanced, objective evaluation. Mediate between the aggressive and conservative positions, weighing evidence fairly.

Be specific. Reference the trader's plan and market data directly.

AGGRESSIVE: [aggressive analyst's full response]
CONSERVATIVE: [conservative analyst's full response]
NEUTRAL: [neutral analyst's full response]"""


def _parse_perspectives(text: str) -> dict[str, str]:
    sections = {"aggressive": "", "conservative": "", "neutral": ""}
    for key in sections:
        heading = key.upper()
        # Match the heading allowing optional markdown bold (**HEADING:** or **HEADING**:)
        # and capture everything up to the next heading or end-of-string.
        # Handles: AGGRESSIVE:, **AGGRESSIVE:**, **AGGRESSIVE**:, AGGRESSIVE :, etc.
        pattern = rf"(?:^|\n)\*{{0,2}}{re.escape(heading)}\*{{0,2}}\s*:\s*(.*?)(?=\n\*{{0,2}}(?:AGGRESSIVE|CONSERVATIVE|NEUTRAL)\*{{0,2}}\s*:|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            sections[key] = m.group(1).strip()
    return sections


def create_risk_debate_node(ctx: AgentRunContext) -> NodeFn:
    from backend.trading_agents.agents.runtime.report_aggregator import (
        build_report_fields,
        build_resources,
    )

    async def risk_debate_node(state) -> dict:
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[risk_debate] branch disabled — skipping risk debate.")
            return {"risk_debate_state": neutral_risk_debate_state("")}

        llm = ctx.llm_for("risk_debate")

        trader_decision = state.get("trader_investment_plan", "No trader decision available.")
        report_fields = build_report_fields("Latest World Affairs Report", "Company Fundamentals Report")
        resources_text = build_resources(state, report_fields, summary_only=True)
        prompt = _build_merged_prompt(trader_decision, resources_text)

        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        sections = _parse_perspectives(text)

        aggressive_arg = f"Aggressive Analyst: {sections['aggressive']}" if sections["aggressive"] else ""
        conservative_arg = f"Conservative Analyst: {sections['conservative']}" if sections["conservative"] else ""
        neutral_arg = f"Neutral Analyst: {sections['neutral']}" if sections["neutral"] else ""

        history_parts = [p for p in (aggressive_arg, conservative_arg, neutral_arg) if p]
        history = "\n".join(history_parts)

        risk_debate_state = {
            "aggressive_history": aggressive_arg,
            "conservative_history": conservative_arg,
            "neutral_history": neutral_arg,
            "history": history,
            "latest_speaker": "Neutral",
            "current_aggressive_response": aggressive_arg,
            "current_conservative_response": conservative_arg,
            "current_neutral_response": neutral_arg,
            "judge_decision": "",
            "count": 3,
        }

        return {"risk_debate_state": risk_debate_state}

    return risk_debate_node
