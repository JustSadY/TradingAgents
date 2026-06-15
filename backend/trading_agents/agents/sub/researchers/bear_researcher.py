from backend.trading_agents.agents.runtime.report_aggregator import (
    build_report_fields,
    build_resources,
    tail_history,
)
from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block


def create_bear_researcher(llm):
    async def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        current_response = investment_debate_state.get("current_response", "")
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = "Company fundamentals report" if asset_type == "stock" else "Asset fundamentals report"
        report_fields = build_report_fields("Latest World Affairs News", fundamentals_label)
        synthesis_report = state.get("synthesis_report", "No synthesis report available.")
        qa = state.get("agent_qa_report") or ""
        qa_block = f"\n### Analyst Cross-Examination (peer Q&A that probed these conflicts):\n{qa}\n" if qa else ""
        resources_text = build_resources(state, report_fields)

        prompt = f"""You are a High-Conviction Bear Analyst making the case against investing in the {target_label}. Your goal is to present a rigorous, evidence-based argument emphasizing risks, structural challenges, and negative catalysts.

### Objective:
- **Evidence-Based Case:** You MUST cite specific analyst reports and metrics (e.g., "The Fundamentals report shows a high debt-to-equity...") for every claim you make.
- **Address Conflicts:** Review the **Synthesis Report** below. You must directly address the 'Critical Conflicts' identified and explain why the bearish risks are too high to ignore.
- **Adversarial Debate:** Critically analyze the Bull Analyst's points. Do not just list data; dismantle their growth assumptions with specific evidence.

### Resources:
{resources_text}

### Synthesis Report (Conflicts & Alignments):
{synthesis_report}
{qa_block}
### Debate Context:
- **Conversation History:** {tail_history(history)}
- **Last Bull Argument:** {current_response}

### Guidelines:
- **Risks and Challenges:** Highlight market saturation, financial instability, or macroeconomic threats.
- **Competitive Weaknesses:** Emphasize declining innovation, weak market positioning, or competitive threats.
- **Negative Indicators:** Use evidence from technical breakdowns, sentiment shifts, or adverse news.
- **Tone:** Skeptical, analytical, and professional.

Deliver a compelling bear argument that dismantling the bull case using specific citations.
""" + get_general_settings_block()
        response = await llm.ainvoke(prompt)
        argument = f"Bear Analyst: {response.content}"
        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }
        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
