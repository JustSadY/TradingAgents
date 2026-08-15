"""Task-scoped liveness tracking for long-running analysis jobs.

LangGraph only yields a state update after a node finishes.  An LLM or tool can
be actively working for a while before that happens, so using state updates as
the sole heartbeat source makes healthy work look stalled.  Each analysis run
owns one :class:`AnalysisActivityTracker` and shares it with its callbacks and
graph context.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class AnalysisActivityTracker:
    """Record the most recent meaningful activity in one analysis task.

    Callback implementations are normally invoked on the event loop, but a
    provider integration may report a lifecycle event from a worker thread.
    A tiny lock keeps the timestamp safe in either case.  ``monotonic`` avoids
    false stalls if the wall clock changes while a run is active.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._last_activity_at = clock()

    def touch(self) -> None:
        """Mark this task as active."""
        with self._lock:
            self._last_activity_at = self._clock()

    def last_activity_at(self) -> float:
        """Return the last activity time using the tracker's monotonic clock."""
        with self._lock:
            return self._last_activity_at

def touch_current_analysis() -> None:
    """Best-effort liveness update for code running inside an analysis graph.

    The graph runtime stores the task-local tracker in ``active_run_context``.
    This helper intentionally has no dependency on the caller's execution
    model, so it is also safe from a thread-backed tool wrapper.
    """
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        context = active_run_context.get(None) or {}
        tracker = context.get("activity_tracker")
        if isinstance(tracker, AnalysisActivityTracker):
            tracker.touch()
    except Exception:
        return
