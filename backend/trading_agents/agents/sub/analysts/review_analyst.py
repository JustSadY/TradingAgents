from langchain_core.messages import AIMessage

from backend.trading_agents.agents.analyst_registry import register_analyst
from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.data.review_tools import get_past_performance_data
from backend.trading_agents.agents.runtime.agent_states import AgentState
from backend.trading_agents.agents.runtime.analyst_cache import (
    check_analyst_cache,
    compute_data_hash,
    emit_cache_hit,
    store_analyst_cache,
)
from backend.trading_agents.agents.runtime.analyst_node_factory import run_tool_analyst
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_system_instruction_override,
)

_REVIEW_TOOLS = [get_past_performance_data, run_strategy_backtest]


@register_analyst(
    key="review",
    agent_node="Performance Review Analyst",
    clear_node="Msg Clear Review",
    tool_node="tools_review",
    report_key="review_report",
    tools=_REVIEW_TOOLS,
)
def create_review_analyst(llm):
    async def review_analyst(state: AgentState):
        ticker = state.get("company_of_interest", "Unknown")
        asset_type = state.get("asset_type", "stock")
        context_str = build_instrument_context(ticker, asset_type)
        curr_date = state.get("trade_date")

        performance_data = await get_past_performance_data.ainvoke({"ticker": ticker, "curr_date": curr_date})
        data_hash = compute_data_hash("review", ticker, curr_date, performance_data)

        cached_report = await check_analyst_cache("review", ticker, data_hash)
        if cached_report:
            await emit_cache_hit("review", ticker)
            return {"messages": [AIMessage(content=cached_report)], "review_report": cached_report}

        override = get_system_instruction_override("review")
        if override:
            system_message = override
        else:
            system_message = (
                "You are a senior performance review analyst. Your role is EXCLUSIVELY hindsight audit — you do NOT make buy/sell/hold recommendations. Output only audit observations.\n\n"
                "### Analytical Process (Chain-of-Thought):\n"
                f"1. **Data Retrieval:** Use `get_past_performance_data` with ticker '{ticker}' and date '{curr_date}' to fetch previous analyses and actual price performance.\n"
                "2. **Accuracy Audit:** Compare the past directional call (Buy/Sell/Hold) against the actual Alpha and raw returns. Classify each past call as correct/incorrect/partial.\n"
                "3. **Thesis Validation:** Determine which specific parts of the past investment thesis held true and which failed. Assign a confidence level to each assessment.\n"
                "4. **Bias Detection:** Identify any recurring patterns in past errors (e.g., systematic over-optimism, under-reaction to macro shifts).\n"
                "5. **Learning Synthesis:** Formulate concrete, actionable lessons to be applied to the current analysis cycle.\n\n"
                "### Guidelines:\n"
                "- If the tool returns no data, output: 'No past analysis data available for hindsight review.'\n"
                "- Do NOT provide a new trading decision; focus strictly on the audit.\n"
                "- Be critical and evidence-based.\n"
                "- Distinguish between bad luck (correct reasoning, wrong outcome) and bad process (flawed reasoning).\n"
                "- Assign a confidence level (HIGH/MEDIUM/LOW) to each audit finding.\n\n"
                "### Output Format:\n"
                "Your final report MUST follow this structure:\n"
                "1. **Audit Executive Summary:** A 3-bullet point summary of past performance accuracy and primary lessons, each with confidence.\n"
                "2. **Hindsight Analysis:** Detailed comparison of past thesis vs. actual outcome, citing specific returns and reasoning correctness.\n"
                "3. **Error Pattern Analysis:** Recurring strengths and weaknesses in the analytical process, if identifiable.\n"
                "4. **Lessons Learned:** Specific, actionable advice for the current day's analysts and managers.\n"
                "5. **Performance Audit Table:** A Markdown table summarizing the past decision, actual return, audit status (Correct/Incorrect/Partial), reasoning quality, and confidence.\n"
                f"{context_str}\n"
            )

        # Do not bypass the shared report boundary.  A direct ``response.content``
        # assignment used to let blank/block-shaped provider output become a
        # silently empty report.  The common runner also retains the ToolNode
        # loop, retries transient LLM failures, and emits a visible degraded
        # report if its bounded recovery cannot obtain readable text.
        result = await run_tool_analyst(
            llm,
            state,
            tools=_REVIEW_TOOLS,
            system_message=system_message,
            report_key="review_report",
            instrument_context=context_str,
        )
        report_text = result.get("review_report", "")
        if report_text and "unavailable" not in report_text[:50].lower():
            await store_analyst_cache("review", ticker, data_hash, report_text)
        return result

    return review_analyst
