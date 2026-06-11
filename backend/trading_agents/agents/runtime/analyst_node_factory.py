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

# Shared scaffold wrapped around every tool-using analyst's own system_message.
# Rewording this changes every tool-using analyst's prompt (intentional).
_COLLAB_SYSTEM = (
    "You are a specialist analyst on a trading research team. First call the tools you need to gather"
    " real data, then write a thorough, self-contained report for your role — do not leave gaps for"
    " someone else to fill in. Ground every claim in data you actually retrieved: quote concrete"
    " figures, and if a tool fails or data is unavailable, state that explicitly instead of inventing"
    " numbers. Be decisive and specific; avoid vague hedging."
    " You have access to the following tools: {tool_names}.\n{system_message}\n"
    "For your reference, the current date is {current_date}. {instrument_context}"
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
    from backend.trading_agents.agents.data.chart_tools import active_run_context

    ctx = active_run_context.get(None)
    if ctx and "graph" in ctx:
        graph = ctx["graph"]
        analyst_key = report_key.replace("_report", "")
        tools = graph._filter_tools_for_analyst(analyst_key, tools)

    effective_collab_system = collab_system
    if not effective_collab_system and ctx and "graph" in ctx:
        graph = ctx["graph"]
        runtime_agent_ctx = (getattr(graph, "config", {}) or {}).get("runtime_agent_context", {})
        analyst_key = report_key.replace("_report", "")
        agent_state = runtime_agent_ctx.get(analyst_key, {}) if isinstance(runtime_agent_ctx, dict) else {}
        settings = agent_state.get("settings", {}) if isinstance(agent_state, dict) else {}
        candidate = settings.get("collab_system_prompt") if isinstance(settings, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            effective_collab_system = candidate.strip()

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
    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
    prompt = prompt.partial(current_date=state["trade_date"])
    prompt = prompt.partial(instrument_context=instrument_context)

    # Bind tools only if we have at least one tool
    if tools:
        bound_llm = llm.bind_tools(tools)
    else:
        bound_llm = llm

    import time as _time

    from langchain_core.messages import AIMessage

    from backend.trading_agents.agents.runtime.resilience import log_event, retry_call

    analyst = report_key.replace("_report", "")
    _start = _time.time()
    log_event("node_start", node=analyst, kind="analyst")

    # Progress: Emit analyst progress event
    if ctx and "emitter" in ctx:
        emitter = ctx["emitter"]
        from backend.core.catalog import node_progress
        prog = node_progress(f"{analyst}_analyst")
        if prog:
            await emitter.emit(prog)

    # Mental Model: Emit thinking event
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
        # Use ainvoke directly for better consistency and to stay on the main loop
        result = await retry_call(
            lambda: (prompt | bound_llm).ainvoke(state["messages"]),
            label=f"analyst:{analyst}",
            run_in_thread=False,
            runtime_config=runtime_retry_config,
        )
    except Exception as exc:  # noqa: BLE001
        # Retries exhausted — skip this analyst with a visible note instead of
        # aborting the whole run. The empty AIMessage carries no tool calls, so
        # the graph routes straight to the next analyst.
        import traceback as _tb

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
    log_event("node_end", node=analyst, kind="analyst", ms=int((_time.time() - _start) * 1000))
    report = result.content if len(result.tool_calls) == 0 else ""
    return {"messages": [result], report_key: report}
