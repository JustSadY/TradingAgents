from backend.trading_agents.agents.utils.agent_utils import get_language_instruction
from backend.trading_agents.agents.runtime.report_aggregator import build_resources
def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")
        current_response = investment_debate_state.get("current_response", "")
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report"
        )
        report_fields = {
            "market_report": "Market Research Report",
            "sentiment_report": "Social Media Sentiment Report",
            "news_report": "Latest World Affairs News",
            "fundamentals_report": fundamentals_label,
            "macro_report": "Macroeconomic Indicators Report",
            "options_report": "Options Market Derivatives Report",
            "quant_report": "Quantitative Metrics Report",
            "earnings_report": "Corporate Guidance & Earnings Report",
            "review_report": "Hindsight Performance Review Report",
        }
        synthesis_report = state.get("synthesis_report", "No synthesis report available.")
        resources_text = build_resources(state, report_fields)
        
        prompt = f"""You are a High-Conviction Bull Analyst advocating for a long position in the {target_label}. Your task is to build a rigorous, evidence-based case emphasizing growth potential and market strength.

### Objective:
- **Evidence-Based Case:** You MUST cite specific analyst reports and metrics (e.g., "According to the Market Analyst, the 50 SMA...") for every claim you make.
- **Address Conflicts:** Review the **Synthesis Report** below. You must directly address the 'Critical Conflicts' identified and explain why the bullish perspective is more compelling despite these risks.
- **Adversarial Debate:** Critically analyze the Bear Analyst's points. Do not just list data; dismantle their logic with specific data points.

### Resources:
{resources_text}

### Synthesis Report (Conflicts & Alignments):
{synthesis_report}

### Debate Context:
- **Conversation History:** {history}
- **Last Bear Argument:** {current_response}

### Guidelines:
- **Growth Potential:** Highlight market opportunities, revenue projections, and scalability.
- **Competitive Advantages:** Emphasize unique products, branding, or market dominance.
- **Positive Indicators:** Use financial health, industry trends, and technical breakouts as evidence.
- **Tone:** Professional, analytical, and persuasive.

Deliver a compelling bull argument that refutes the bear's concerns using specific citations.
""" + get_language_instruction()
        response = llm.invoke(prompt)
        argument = f"Bull Analyst: {response.content}"
        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }
        return {"investment_debate_state": new_investment_debate_state}
    return bull_node
