"""Shared factory for the bull / bear researchers.

The two researchers are identical except for their stance prompt and which
debate-history field they own. This module holds the one copy of the node
mechanics (asset labelling, resource + synthesis + Q&A assembly, and the
investment-debate-state plumbing); each researcher module supplies only its
side, speaker label and prompt builder.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.trading_agents.agents.runtime.report_aggregator import (
    build_report_fields,
    build_resources,
    tail_history,
)
from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block, get_system_instruction_override

# A prompt builder receives (instruction, target_label, resources_text,
# synthesis_report, qa_block, recent_history, last_opposing_argument) and
# returns the prompt body. ``instruction`` is either this agent's Settings ->
# Agents "System Prompt Override" (verbatim) or the rendered default.
PromptBuilder = Callable[[str, str, str, str, str, str, str], str]
# Renders this researcher's default opening instruction for a given target_label.
DefaultInstruction = Callable[[str], str]


def make_researcher(
    side: str, speaker: str, build_prompt: PromptBuilder, default_instruction: DefaultInstruction
) -> Callable:
    """Build a ``create_<side>_researcher(llm)`` factory (``side`` is bull/bear)."""
    from backend.trading_agents.agents.utils.agent_utils import get_system_instruction_override

    def create_researcher(llm):
        async def researcher_node(state) -> dict:
            investment_debate_state = state["investment_debate_state"]
            history = investment_debate_state.get("history", "")
            own_history = investment_debate_state.get(f"{side}_history", "")
            current_response = investment_debate_state.get("current_response", "")

            asset_type = state.get("asset_type", "stock")
            target_label = "stock" if asset_type == "stock" else "asset"
            fundamentals_label = "Company fundamentals report" if asset_type == "stock" else "Asset fundamentals report"
            report_fields = build_report_fields("Latest World Affairs News", fundamentals_label)
            synthesis_report = state.get("synthesis_report", "No synthesis report available.")
            qa = state.get("agent_qa_report") or ""
            qa_block = f"\n### Analyst Cross-Examination (peer Q&A that probed these conflicts):\n{qa}\n" if qa else ""
            from backend.trading_agents.dataflows.config import get_config
            summary_only = get_config().get("summary_only_mode", False)
            resources_text = build_resources(state, report_fields, summary_only=summary_only)

            instruction = get_system_instruction_override(f"{side}_researcher") or default_instruction(target_label)
            prompt = (
                build_prompt(
                    instruction,
                    target_label,
                    resources_text,
                    synthesis_report,
                    qa_block,
                    tail_history(history),
                    current_response,
                )
                + get_general_settings_block()
            )
            response = await llm.ainvoke(prompt)
            argument = f"{speaker} Analyst: {response.content}"
            other = "bear" if side == "bull" else "bull"
            new_investment_debate_state = {
                "history": history + "\n" + argument,
                f"{side}_history": own_history + "\n" + argument,
                f"{other}_history": investment_debate_state.get(f"{other}_history", ""),
                "current_response": argument,
                "count": investment_debate_state["count"] + 1,
            }
            return {"investment_debate_state": new_investment_debate_state}

        return researcher_node

    return create_researcher
