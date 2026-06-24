from langchain_core.messages import SystemMessage

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.review_tools import get_past_performance_data
from backend.trading_agents.agents.runtime.agent_states import AgentState
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
)

# Single source of truth shared by the ToolNode registration and the LLM binding.
_REVIEW_TOOLS = [get_past_performance_data]


@register_analyst(
    key="review",
    agent_node="Performance Review Analyst",
    clear_node="Msg Clear Review",
    tool_node="tools_review",
    report_key="review_report",
    tools=_REVIEW_TOOLS,
)
def create_review_analyst(llm):
    llm_with_tools = llm.bind_tools(_REVIEW_TOOLS)

    async def review_analyst(state: AgentState):
        ticker = state.get("company_of_interest", "Unknown")
        asset_type = state.get("asset_type", "stock")
        context_str = build_instrument_context(ticker, asset_type)
        curr_date = state.get("trade_date")

        system_message = (
            "You are a senior performance review analyst. Your goal is to conduct a rigorous hindsight audit of past trading decisions to drive system improvement.\n\n"
            "### Analytical Process (Chain-of-Thought):\n"
            f"1. **Data Retrieval:** Use `get_past_performance_data` with ticker '{ticker}' and date '{curr_date}' to fetch previous analyses and actual price performance.\n"
            "2. **Accuracy Audit:** Compare the past directional call (Buy/Sell/Hold) against the actual Alpha and raw returns.\n"
            "3. **Thesis Validation:** Determine which specific parts of the past investment thesis held true and which failed.\n"
            "4. **Learning Synthesis:** Formulate concrete, actionable lessons to be applied to the current analysis cycle.\n\n"
            "### Guidelines:\n"
            "- If the tool returns no data, output: 'No past analysis data available for hindsight review.'\n"
            "- Do NOT provide a new trading decision; focus strictly on the audit.\n"
            "- Be critical and evidence-based.\n\n"
            "### Output Format:\n"
            "Your final report MUST follow this structure:\n"
            "1. **Audit Executive Summary:** A 3-bullet point summary of past performance accuracy and primary lessons.\n"
            "2. **Hindsight Analysis:** Detailed comparison of past thesis vs. actual outcome, citing specific returns.\n"
            "3. **Lessons Learned:** Specific, actionable advice for the current day's analysts and managers.\n"
            "4. **Performance Audit Table:** A Markdown table summarizing the past decision, actual return, and audit status (Correct/Incorrect/Partial).\n"
            f"{context_str}\n"
        )

        messages = [
            SystemMessage(content=system_message),
            *state["messages"],
        ]

        # Use ainvoke for async compatibility
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response], "review_report": response.content}

    return review_analyst
