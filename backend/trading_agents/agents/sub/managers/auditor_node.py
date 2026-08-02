from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_system_instruction_override,
)

# The bull/bear researchers are handed these two documents alongside the
# analyst reports and are explicitly instructed to cite them.  Auditing the
# debate against the analyst reports alone therefore flagged every legitimate
# citation of them as a hallucination, and the resulting Final Auditor Note
# told the Research Manager to discard sound, grounded arguments.  The auditor
# must see exactly the same ground truth the debaters were given.
_DEBATE_SOURCE_DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("Synthesis Report (Conflicts & Alignments)", "synthesis_report"),
    ("Analyst Cross-Examination (peer Q&A)", "agent_qa_report"),
)


def _with_debate_source_documents(state, resources_text: str) -> str:
    """Append the non-analyst documents the debaters were allowed to cite."""
    sections = [resources_text] if resources_text.strip() else []
    for label, field in _DEBATE_SOURCE_DOCUMENTS:
        content = (state.get(field) or "").strip()
        if content:
            sections.append(f"### {label}:\n{content}")
    return "\n\n".join(sections)


def create_auditor_node(llm):
    async def auditor_node(state) -> dict:
        from backend.trading_agents.dataflows.config import get_config

        if not get_config().get("auditor_enabled", True):
            return {"audit_report": "Audit disabled by user settings."}

        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(ticker, asset_type)

        investment_debate_state = state["investment_debate_state"]
        debate_history = investment_debate_state.get("history", "")

        from backend.trading_agents.agents.analyst_registry import get_report_fields
        from backend.trading_agents.agents.runtime.report_aggregator import build_resources

        summary_only = get_config().get("summary_only_mode", False)
        resources_text = build_resources(state, get_report_fields(), prefix="### ", summary_only=summary_only)
        resources_text = _with_debate_source_documents(state, resources_text)

        default_instruction = (
            f"You are a Senior Compliance Auditor and Fact-Checker. Your goal is to review the investment "
            f"debate for {ticker} and ensure all claims are grounded in the provided analyst reports."
        )
        instruction = get_system_instruction_override("auditor") or default_instruction

        prompt = f"""{instruction}

### Objective:
1. **Hallucination Detection:** Identify any claims, metrics, or prices mentioned in the debate that ARE NOT present in the original analyst reports.
2. **Citation Verification:** Ensure that when an analyst cites a report, the data actually exists in that report.
3. **Reasoning Gap Analysis:** Flag any logical leaps or unsubstantiated conclusions.

### Original Analyst Reports (Ground Truth):
{resources_text}

### Investment Debate Transcript:
{debate_history}

{instrument_context}

### Output Format:
Your audit report MUST follow this structure:
1. **Audit Executive Summary:** A Pass/Fail/Caution rating on the integrity of the debate.
2. **Flagged Hallucinations:** List any specific claims that are unsupported by the ground truth reports.
3. **Verified Evidence:** Confirm the most critical pieces of evidence that WERE correctly cited.
4. **Final Auditor Note:** A directive to the Research Manager on which arguments to ignore or prioritize.

{get_general_settings_block()}
"""
        response = await llm.ainvoke(prompt)
        return {"audit_report": response.content}

    return auditor_node
