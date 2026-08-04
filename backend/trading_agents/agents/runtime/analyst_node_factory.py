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

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

_COLLAB_SYSTEM = (
    "You are a specialist analyst on a trading research team. First call the tools you need to gather"
    " real data, then write a thorough, self-contained report for your role — do not leave gaps for"
    " someone else to fill in. Ground every claim in data you actually retrieved: quote concrete"
    " figures, and if a tool fails or data is unavailable, state that explicitly instead of inventing"
    " numbers. Be decisive and specific; avoid vague hedging."
    " You have access to the following tools: {tool_names}.\n{system_message}\n"
    "For your reference, the current date is {current_date}. {instrument_context}"
)

_logger = logging.getLogger(__name__)


def _report_text(content: Any) -> str:
    """Normalize provider-specific content blocks through the shared parser."""
    from backend.services.analysis.reports import report_text

    return report_text(content)


async def _recover_empty_report(
    *,
    prompt: Any,
    llm: Any,
    state: dict,
    analyst: str,
    runtime_config: dict | None,
) -> str:
    """Make one text-only recovery attempt for an empty final LLM response.

    Tool-capable models can finish a tool round with an empty assistant message
    when a provider's function response is malformed or degraded.  Use the
    plain LLM for the recovery, so it cannot enter another tool loop but can
    still summarize the tool messages already in the conversation.
    """
    from backend.trading_agents.agents.runtime.resilience import retry_call

    messages = state.get("messages") or []
    if isinstance(messages, (list, tuple)):
        messages = list(messages)
    else:
        messages = [messages]

    # Extract meaningful tool data snippets so the recovery prompt has
    # concrete data to summarize even when the message history is long.
    tool_data_snippets: list[str] = []
    for m in messages:
        content = getattr(m, "content", "")
        if hasattr(m, "type") and getattr(m, "type", None) == "tool" and content:
            snippet = str(content)[:500]
            if len(snippet.strip()) > 50:
                tool_data_snippets.append(snippet)

    extra_context = ""
    if tool_data_snippets:
        extra_context = (
            " Here is a summary of data your tools collected:\n"
            + "\n---\n".join(tool_data_snippets[:3])
            + "\n\nUse this data to write your report."
        )

    recovery_request = HumanMessage(
        content=(
            "Your previous response contained no readable final report. "
            "Return a concise, self-contained analyst report using the data already gathered above. "
            "Keep it under 500 words so the final answer is emitted before any provider output budget is exhausted. "
            "Do not call tools and do not return an empty response."
            + extra_context
        )
    )
    try:
        response = await retry_call(
            lambda: (prompt | llm).ainvoke([*messages, recovery_request]),
            label=f"analyst:{analyst}:empty-report-recovery",
            run_in_thread=False,
            runtime_config=runtime_config,
        )
    except Exception as exc:  # noqa: BLE001 - recovery must never hide the original run state
        _logger.warning("%s returned an empty report and recovery failed: %s", analyst, exc)
        return ""
    return _report_text(getattr(response, "content", ""))


def _empty_report_notice(analyst: str) -> str:
    """Return a visible degraded report instead of a silently blank UI card."""
    return (
        f"⚠️ {analyst.title()} analysis unavailable: the selected model returned no readable final report "
        "after data collection. No conclusion was inferred; retry this analysis or choose another model."
    )


def _tool_turn_count(messages: object) -> int:
    if not isinstance(messages, (list, tuple)):
        return 0
    return sum(1 for message in messages if getattr(message, "tool_calls", None))


def _max_tool_turns(ctx: dict | None) -> int:
    configured = 10
    if ctx and "graph" in ctx:
        try:
            configured = int((getattr(ctx["graph"], "config", {}) or {}).get("max_analyst_tool_turns", 10))
        except (TypeError, ValueError):
            configured = 10
    return max(1, min(configured, 50))


async def run_tool_analyst(
    llm,
    state,
    *,
    tools,
    system_message,
    report_key,
    instrument_context,
    collab_system: str | None = None,
):
    """Run the standard tool-using analyst turn and return its state update."""
    from backend.trading_agents.agents.analyst_registry import analyst_key_for_report
    from backend.trading_agents.agents.data.chart_tools import active_run_context

    # ``sentiment_report`` is produced by the runtime key ``social``. Do not
    # derive policy/telemetry keys from report-field spelling: doing so bypasses
    # the user's Social Analyst model override and can apply the wrong tool
    # access rule after this shared runner is used by that analyst.
    analyst = analyst_key_for_report(report_key) or report_key.replace("_report", "")

    ctx = active_run_context.get(None)
    if ctx and "graph" in ctx:
        graph = ctx["graph"]
        tools = graph._filter_tools_for_analyst(analyst, tools)

    tool_turns = _tool_turn_count(state.get("messages"))
    max_tool_turns = _max_tool_turns(ctx)
    force_finalize = tool_turns >= max_tool_turns
    if force_finalize:
        _logger.warning(
            "%s reached max tool turns (%d); running a tool-free final report pass.",
            analyst,
            max_tool_turns,
        )
        tools = []

    effective_collab_system = collab_system
    effective_system_message = system_message
    if ctx and "graph" in ctx:
        graph = ctx["graph"]
        runtime_agent_ctx = (getattr(graph, "config", {}) or {}).get("runtime_agent_context", {})
        agent_state = runtime_agent_ctx.get(analyst, {}) if isinstance(runtime_agent_ctx, dict) else {}
        settings = agent_state.get("settings", {}) if isinstance(agent_state, dict) else {}
        if isinstance(settings, dict):
            if not effective_collab_system:
                candidate = settings.get("collab_system_prompt")
                if isinstance(candidate, str) and candidate.strip():
                    effective_collab_system = candidate.strip()
            override = settings.get("system_instruction")
            if isinstance(override, str) and override.strip():
                effective_system_message = override.strip()

    effective_collab_system = effective_collab_system or _COLLAB_SYSTEM
    if force_finalize:
        effective_collab_system += (
            "\nTool collection is complete. You MUST now return the final readable report using the tool "
            "results already present in the conversation. Do not request or emit any additional tool call."
        )
    runtime_retry_config = None
    if ctx and "graph" in ctx:
        runtime_retry_config = getattr(ctx["graph"], "config", {}) or {}
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", effective_collab_system),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    prompt = prompt.partial(system_message=effective_system_message + get_general_settings_block())
    prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
    prompt = prompt.partial(current_date=state["trade_date"])
    prompt = prompt.partial(instrument_context=instrument_context)

    if tools:
        bound_llm = llm.bind_tools(tools)
    else:
        bound_llm = llm

    from backend.trading_agents.agents.runtime.resilience import log_event, retry_call

    if ctx and "emitter" in ctx:
        emitter = ctx["emitter"]
        from backend.core.catalog import node_progress

        prog = node_progress(f"{analyst}_analyst")
        if prog:
            await emitter.emit(prog)

    if ctx and "emitter" in ctx:
        emitter = ctx["emitter"]
        thought = f"Examining {state['company_of_interest']} {analyst.title()} data..."
        if analyst == "market":
            thought = f"Analyzing technical indicators and price action for {state['company_of_interest']}..."
        elif analyst == "fundamentals":
            thought = f"Reviewing financial statements and valuation for {state['company_of_interest']}..."
        elif analyst == "news":
            thought = f"Scanning latest news and insider activity for {state['company_of_interest']}..."

        await emitter.emit_mental_model(analyst, thought)

    try:
        invoke_messages = state.get("messages") or []
        if force_finalize:
            invoke_messages = [
                *list(invoke_messages),
                HumanMessage(
                    content=(
                        "Produce the final analyst report now from the evidence above. "
                        "Do not call tools. Explicitly identify unavailable data instead of guessing."
                    )
                ),
            ]
        result = await retry_call(
            lambda: (prompt | bound_llm).ainvoke(invoke_messages),
            label=f"analyst:{analyst}",
            run_in_thread=False,
            runtime_config=runtime_retry_config,
        )
    except Exception as exc:
        import traceback as _tb

        from langchain_core.messages import AIMessage
        from backend.trading_agents.llm_clients.base_client import is_quota_exhausted

        log_event(
            "node_error",
            level=40,
            node=analyst,
            kind="analyst",
            error=str(exc)[:300],
            exc_type=type(exc).__name__,
            traceback=_tb.format_exc()[-1500:],
        )
        log_event("node_skipped", level=30, node=analyst, kind="analyst")

        if is_quota_exhausted(exc):
            _logger.warning(
                "%s skipped due to provider quota exhaustion — recovery not attempted.",
                analyst,
            )

        return {
            "messages": [AIMessage(content="")],
            report_key: (
                f"{analyst.title()} analysis unavailable because the agent failed before "
                "producing a report. Retry the analysis or choose another model."
            ),
        }

    tool_calls = getattr(result, "tool_calls", None) or []
    if tool_calls and not force_finalize:
        return {"messages": [result], report_key: ""}

    report = _report_text(getattr(result, "content", ""))
    if not report:
        _logger.warning("%s returned an empty final report; attempting text-only recovery.", analyst)
        report = await _recover_empty_report(
            prompt=prompt,
            llm=llm,
            state=state,
            analyst=analyst,
            runtime_config=runtime_retry_config,
        )
    if not report:
        report = _empty_report_notice(analyst)
    if force_finalize and tool_calls:
        from langchain_core.messages import AIMessage

        result = AIMessage(content=report)
    return {"messages": [result], report_key: report}
