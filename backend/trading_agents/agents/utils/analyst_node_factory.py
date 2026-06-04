"""Shared scaffold for tool-using analyst nodes.

The market / fundamentals / macro / options / news / quant / earnings analysts
all build the *same* collaborating-assistant prompt, bind their tools, invoke the
LLM, and return ``{"messages": [...], "<report_key>": report}``. Only the system
message, the tool list, the instrument context and the report column differ.

``run_tool_analyst`` is that shared scaffold. The collaborating-assistant system
string below is byte-identical to what each analyst previously inlined, so the
prompt sent to the LLM is unchanged.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Byte-identical to the per-analyst scaffold it replaces — do not reword without
# intending to change every tool-using analyst's prompt.
_COLLAB_SYSTEM = (
    "You are a helpful AI assistant, collaborating with other assistants."
    " Use the provided tools to progress towards answering the question."
    " If you are unable to fully answer, that's OK; another assistant with different tools"
    " will help where you left off. Execute what you can to make progress."
    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
    " You have access to the following tools: {tool_names}.\n{system_message}"
    "For your reference, the current date is {current_date}. {instrument_context}"
)


def run_tool_analyst(llm, state, *, tools, system_message, report_key, instrument_context):
    """Run the standard tool-using analyst turn and return its state update."""
    from backend.trading_agents.agents.utils.chart_tools import active_run_context
    ctx = active_run_context.get(None)
    if ctx and "graph" in ctx:
        graph = ctx["graph"]
        analyst_key = report_key.replace("_report", "")
        tools = graph._filter_tools_for_analyst(analyst_key, tools)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _COLLAB_SYSTEM),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
    prompt = prompt.partial(current_date=state["trade_date"])
    prompt = prompt.partial(instrument_context=instrument_context)

    # Bind tools only if we have at least one tool
    if tools:
        bound_llm = llm.bind_tools(tools)
    else:
        bound_llm = llm

    from backend.trading_agents.agents.utils.resilience import retry_call, log_event
    from langchain_core.messages import AIMessage
    import time as _time
    analyst = report_key.replace("_report", "")
    _start = _time.time()
    log_event("node_start", node=analyst, kind="analyst")
    try:
        result = retry_call(
            lambda: (prompt | bound_llm).invoke(state["messages"]),
            label=f"analyst:{analyst}",
        )
    except Exception as exc:  # noqa: BLE001
        # Retries exhausted — skip this analyst with a visible note instead of
        # aborting the whole run. The empty AIMessage carries no tool calls, so
        # the graph routes straight to the next analyst.
        log_event("node_error", level=40, node=analyst, kind="analyst", error=str(exc)[:300])
        log_event("node_skipped", level=30, node=analyst, kind="analyst")
        return {
            "messages": [AIMessage(content="")],
            report_key: f"⚠️ {analyst.title()} analysis unavailable (agent error: {exc}).",
        }
    log_event("node_end", node=analyst, kind="analyst", ms=int((_time.time() - _start) * 1000))
    report = result.content if len(result.tool_calls) == 0 else ""
    return {"messages": [result], report_key: report}
