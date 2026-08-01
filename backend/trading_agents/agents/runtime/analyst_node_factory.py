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
    """Return displayable text from a final model response.

    Provider clients normalize the common content-list form, but an analyst
    boundary still needs to reject a whitespace-only final message.  A blank
    message is not a completed report.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


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
    recovery_request = HumanMessage(
        content=(
            "Your previous response contained no readable final report. "
            "Return a concise, self-contained analyst report using the data already gathered above. "
            "Keep it under 500 words so the final answer is emitted before any provider output budget is exhausted. "
            "Do not call tools and do not return an empty response."
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
        result = await retry_call(
            lambda: (prompt | bound_llm).ainvoke(state["messages"]),
            label=f"analyst:{analyst}",
            run_in_thread=False,
            runtime_config=runtime_retry_config,
        )
    except Exception as exc:
        import traceback as _tb

        from langchain_core.messages import AIMessage

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
        return {
            "messages": [AIMessage(content="")],
            report_key: f"{analyst.title()} analysis unavailable (agent error: {exc}).",
        }

    tool_calls = getattr(result, "tool_calls", None) or []
    if tool_calls:
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
    return {"messages": [result], report_key: report}
