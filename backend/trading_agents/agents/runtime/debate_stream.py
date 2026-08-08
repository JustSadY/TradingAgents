"""Live debate event bridge for imperative sub-agent loops.

Some debate loops run *inside* one LangGraph node. LangGraph only exposes that
node's state update after the node returns, which is too late for a live UI.
This helper emits complete debate turns directly through the current run's
AnalysisEmitter while keeping persistence in the outer orchestrator.

The current run context records the highest emitted turn count per debate type,
and the emitter marks each live event for one later graph-observer replay
suppression. This keeps the UI live without duplicating the same turn when the
enclosing node finally returns.
"""

from __future__ import annotations

from collections.abc import Mapping

from backend.trading_agents.agents.runtime.debate_history import debate_messages


async def emit_live_debate_state(debate_type: str, state: Mapping[str, object] | None) -> int:
    """Emit newly appended debate turns and return the number emitted.

    This function intentionally performs no database I/O. Graph nodes may run
    in tasks separate from the analysis orchestrator, and sharing its
    ``AsyncSession`` across those tasks would introduce a new concurrency
    hazard. Durable debate history remains the orchestrator observer's job.
    """

    if not state:
        return 0

    from backend.trading_agents.agents.data.chart_tools import active_run_context

    runtime = active_run_context.get(None)
    if not isinstance(runtime, dict):
        return 0
    emitter = runtime.get("emitter")
    if emitter is None or not hasattr(emitter, "emit_debate_bubble"):
        return 0

    try:
        current_count = max(0, int(state.get("count", 0) or 0))
    except (TypeError, ValueError):
        current_count = 0

    counts = runtime.setdefault("debate_streamed_counts", {})
    if not isinstance(counts, dict):
        counts = {}
        runtime["debate_streamed_counts"] = counts
    try:
        previous_count = max(0, int(counts.get(debate_type, 0) or 0))
    except (TypeError, ValueError):
        previous_count = 0

    if current_count <= previous_count:
        return 0

    messages = debate_messages(state.get("history", ""))
    if not messages:
        # Advance the watermark so a malformed/empty fallback state cannot be
        # emitted repeatedly by the enclosing node itself.
        counts[debate_type] = current_count
        return 0

    newly_added = min(len(messages), max(1, current_count - previous_count))
    emitted = 0
    for message in messages[-newly_added:]:
        await emitter.emit_debate_bubble(
            debate_type,
            f"{message['sender']}: {message['content']}",
            sender=message["sender"],
            content=message["content"],
            expect_graph_replay=True,
        )
        emitted += 1

    counts[debate_type] = current_count
    tracker = runtime.get("activity_tracker")
    touch = getattr(tracker, "touch", None)
    if callable(touch):
        touch()
    return emitted
