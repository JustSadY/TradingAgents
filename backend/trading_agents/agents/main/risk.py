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
from backend.trading_agents.agents.runtime.debate_history import (
    format_debate_argument,
    text_from_response,
)
from backend.trading_agents.agents.utils.agent_utils import (
    get_general_settings_block,
    get_system_instruction_override,
)

logger = logging.getLogger(__name__)

MAIN_KEY = "risk_debate"

def _build_merged_prompt(
    research_evidence: str,
    resources_text: str,
    custom_instruction: str | None = None,
) -> str:
    custom_instruction_block = (
        f"\nPANEL-SPECIFIC INSTRUCTION:\n{custom_instruction.strip()}\n" if custom_instruction else ""
    )
    return f"""You are the Risk Debate Panel consisting of three analysts evaluating research evidence and portfolio guardrails.

RESEARCH MANAGER EVIDENCE BRIEF (NON-EXECUTABLE):
{research_evidence}

MARKET DATA & ANALYSIS:
{resources_text}

INSTRUCTIONS:
Provide all three risk perspectives in the following exact plain-text layout.
Use each label once, put the response below it, and do not add Markdown bold,
headings, asterisks, or alternative speaker labels.

AGGRESSIVE:
[full aggressive perspective]

CONSERVATIVE:
[full conservative perspective]

NEUTRAL:
[full neutral perspective]

The aggressive perspective champions well-supported upside but must name the
risks it accepts. The conservative perspective prioritizes capital preservation
and concrete downside scenarios. The neutral perspective weighs both sides and
states practical guardrails. Be specific and reference the research evidence
and market data directly. Do not issue Buy, Overweight, Hold, Underweight, or
Sell; do not prescribe a quantity, allocation, entry, stop, target, or leverage.
The Portfolio Manager is the sole final decision and execution authority.{custom_instruction_block}"""

def _parse_perspectives(text: str) -> dict[str, str]:
    """Extract risk panel sections from strict and common provider variants.

    A number of providers return Markdown headings such as
    ``**Aggressive Risk Analyst**`` despite the requested ``AGGRESSIVE:``
    layout.  Treat those variants as equivalent so one formatting choice never
    erases the entire risk debate.
    """
    sections = {"aggressive": "", "conservative": "", "neutral": ""}
    if not text:
        return sections

    heading_names = "aggressive|conservative|neutral"
    header = re.compile(
        rf"^[ \t]*(?:#{{1,6}}[ \t]+)?(?:\*{{1,3}}[ \t]*)?"
        rf"(?P<key>{heading_names})(?:[ \t]+(?:risk[ \t]+)?(?:analyst|debator))?"
        rf"(?:[ \t]*\*{{1,3}})?[ \t]*(?::|[—–-][ \t]+|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(header.finditer(text))
    for index, match in enumerate(matches):
        key = match.group("key").lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[key] = text[match.end() : end].strip(" \t\n:—–-")
    return sections

def create_risk_debate_node(ctx: AgentRunContext) -> NodeFn:
    from backend.trading_agents.agents.analyst_registry import get_report_fields
    from backend.trading_agents.agents.runtime.report_aggregator import (
        build_resources,
    )

    async def risk_debate_node(state) -> dict:
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[risk_debate] branch disabled — skipping risk debate.")
            return {"risk_debate_state": neutral_risk_debate_state("")}

        llm = ctx.llm_for("risk_debate")

        research_evidence = state.get("investment_plan", "No research evidence brief available.")
        resources_text = build_resources(state, get_report_fields(), summary_only=True)
        custom_instruction = get_system_instruction_override(MAIN_KEY)
        prompt = (
            _build_merged_prompt(research_evidence, resources_text, custom_instruction) + get_general_settings_block()
        )

        response = await llm.ainvoke(prompt)
        text = text_from_response(response)
        sections = _parse_perspectives(text)

        aggressive_arg = format_debate_argument("Aggressive Analyst", sections["aggressive"])
        conservative_arg = format_debate_argument("Conservative Analyst", sections["conservative"])
        neutral_arg = format_debate_argument("Neutral Analyst", sections["neutral"])

        if not any((aggressive_arg, conservative_arg, neutral_arg)):
            neutral_arg = format_debate_argument(
                "Neutral Analyst",
                text,
                empty_notice="Risk Debate did not return a readable structured response.",
            )

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
