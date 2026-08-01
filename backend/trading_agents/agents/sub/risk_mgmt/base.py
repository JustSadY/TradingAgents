"""Shared factory for the three risk debators.

Aggressive / conservative / neutral debators are identical except for their
stance prompt and which sibling responses they read. This module holds the one
copy of the node mechanics (resource assembly + risk-debate-state plumbing);
each debator module just supplies its stance, speaker label and prompt builder.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.trading_agents.agents.runtime.debate_history import format_debate_argument
from backend.trading_agents.agents.runtime.report_aggregator import (
    build_resources,
    tail_history,
)
from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

PromptBuilder = Callable[[str, str, str, str, dict], str]
DefaultInstruction = Callable[[], str]

_SETTINGS_AGENT_KEY = "risk_debate"

def make_risk_debator(
    stance: str, speaker: str, build_prompt: PromptBuilder, default_instruction: DefaultInstruction
) -> Callable:
    """Build a ``create_<stance>_debator(llm)`` factory.

    ``stance`` is one of ``aggressive`` / ``conservative`` / ``neutral`` and keys
    the per-stance ``*_history`` / ``current_*_response`` fields it owns.
    """
    from backend.trading_agents.agents.utils.agent_utils import get_system_instruction_override

    def create_debator(llm):
        async def debator_node(state) -> dict:
            risk_debate_state = state["risk_debate_state"]
            history = risk_debate_state.get("history", "")
            own_history = risk_debate_state.get(f"{stance}_history", "")
            research_evidence = state.get("investment_plan", "No research evidence brief available.")

            from backend.trading_agents.agents.analyst_registry import get_report_fields

            resources_text = build_resources(state, get_report_fields(), summary_only=True)

            instruction = get_system_instruction_override(_SETTINGS_AGENT_KEY) or default_instruction()
            prompt = (
                build_prompt(instruction, research_evidence, resources_text, tail_history(history), risk_debate_state)
                + get_general_settings_block()
            )

            response = await llm.ainvoke(prompt)
            argument = format_debate_argument(
                f"{speaker} Analyst",
                response,
                empty_notice=f"{speaker} perspective was unavailable for this debate turn.",
            )

            new_risk_debate_state = {
                "history": history + "\n" + argument,
                "aggressive_history": risk_debate_state.get("aggressive_history", ""),
                "conservative_history": risk_debate_state.get("conservative_history", ""),
                "neutral_history": risk_debate_state.get("neutral_history", ""),
                "latest_speaker": speaker,
                "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
                "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
                "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
                "count": risk_debate_state["count"] + 1,
            }
            new_risk_debate_state[f"{stance}_history"] = own_history + "\n" + argument
            new_risk_debate_state[f"current_{stance}_response"] = argument
            return {"risk_debate_state": new_risk_debate_state}

        return debator_node

    return create_debator
