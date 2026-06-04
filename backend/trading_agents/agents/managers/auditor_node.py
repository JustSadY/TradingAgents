from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)

def create_auditor_node(llm):
    def auditor_node(state) -> dict:
        from backend.trading_agents.dataflows.config import get_config
        if not get_config().get("auditor_enabled", True):
            return {"audit_report": "Audit disabled by user settings."}

        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(ticker, asset_type)
        
        investment_debate_state = state["investment_debate_state"]
        debate_history = investment_debate_state.get("history", "")
        
        report_fields = {
            "market_report": "Market Research Report",
            "sentiment_report": "Social Media Sentiment Report",
            "news_report": "Latest World Affairs News",
            "fundamentals_report": "Fundamentals Report",
            "macro_report": "Macroeconomic Indicators Report",
            "options_report": "Options Market Derivatives Report",
            "quant_report": "Quantitative Metrics Report",
            "earnings_report": "Corporate Guidance & Earnings Report",
            "review_report": "Hindsight Performance Review Report",
        }
        
        resources = []
        for field, label in report_fields.items():
            content = state.get(field, "")
            if content and content.strip():
                resources.append(f"### {label}:\n{content.strip()}")
        
        resources_text = "\n\n".join(resources)
        
        prompt = f"""You are a Senior Compliance Auditor and Fact-Checker. Your goal is to review the investment debate for {ticker} and ensure all claims are grounded in the provided analyst reports.

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

{get_language_instruction()}
"""
        response = llm.invoke(prompt)
        return {"audit_report": response.content}
    
    return auditor_node
