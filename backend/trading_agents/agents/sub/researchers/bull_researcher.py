from backend.trading_agents.agents.sub.researchers.base import make_researcher


def _default_instruction(target_label: str) -> str:
    return (
        f"You are a High-Conviction Bull Analyst advocating for a long position in the {target_label}. "
        "Your task is to build a rigorous, evidence-based case emphasizing growth potential and market strength."
    )


def _build_prompt(
    instruction: str,
    target_label: str,
    resources_text: str,
    synthesis_report: str,
    qa_block: str,
    recent_history: str,
    last_opposing_argument: str,
) -> str:
    return f"""{instruction}

### Objective:
- **Evidence-Based Case:** You MUST cite specific analyst reports and metrics (e.g., "According to the Market Analyst, the 50 SMA...") for every claim you make.
- **Address Conflicts:** Review the **Synthesis Report** below. You must directly address the 'Critical Conflicts' identified and explain why the bullish perspective is more compelling despite these risks.
- **Adversarial Debate:** Critically analyze the Bear Analyst's points. Do not just list data; dismantle their logic with specific data points.

### Resources:
{resources_text}

### Synthesis Report (Conflicts & Alignments):
{synthesis_report}
{qa_block}
### Debate Context:
- **Conversation History:** {recent_history}
- **Last Bear Argument:** {last_opposing_argument}

### Guidelines:
- **Growth Potential:** Highlight market opportunities, revenue projections, and scalability.
- **Competitive Advantages:** Emphasize unique products, branding, or market dominance.
- **Positive Indicators:** Use financial health, industry trends, and technical breakouts as evidence.
- **Tone:** Professional, analytical, and persuasive.

Deliver a compelling bull argument that refutes the bear's concerns using specific citations.
"""


create_bull_researcher = make_researcher("bull", "Bull", _build_prompt, _default_instruction)
