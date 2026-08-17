"""Terminal state coordination for analysis tasks.

Runtime storage is extracted under ``backend.analysis_runtime``. This module
keeps only the process-local one-shot transition guard used by the service
until terminal coordination itself moves behind the runtime facade.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from backend.analysis_runtime.models import AnalysisTaskStatus, TerminalResult

__all__ = ["AnalysisTaskStatus", "TerminalCoordinator", "TerminalResult"]


class TerminalCoordinator:
    """Run terminal cleanup at most once for each task registration.

    A task id can be registered again only after ``reset``. The bounded result
    history prevents a long-lived web/worker process from accumulating every
    task id it has ever seen while still making duplicate terminal calls a
    no-op during the period where races are realistic.
    """

    def __init__(self, *, history_limit: int = 4096) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self._history_limit = history_limit
        self._results: OrderedDict[str, TerminalResult] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    def reset(self, task_id: str) -> None:
        """Start a fresh lifecycle for ``task_id`` before queued/running registration."""
        self._results.pop(task_id, None)

    def result(self, task_id: str) -> TerminalResult | None:
        return self._results.get(task_id)

    async def run_once(
        self,
        task_id: str,
        result: TerminalResult,
        cleanup: Callable[[], Awaitable[None]],
    ) -> bool:
        """Execute ``cleanup`` once and remember the winning terminal result.

        Returns ``True`` only to the caller that performed cleanup. If cleanup
        raises, no terminal result is recorded so a later caller can retry the
        cleanup rather than leaving partially-cleared runtime state forever.
        """
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            if task_id in self._results:
                return False

            await cleanup()
            self._results[task_id] = result
            self._results.move_to_end(task_id)
            self._trim_history()
            return True

    def _trim_history(self) -> None:
        while len(self._results) > self._history_limit:
            task_id, _ = self._results.popitem(last=False)
            lock = self._locks.get(task_id)
            if lock is not None and not lock.locked():
                self._locks.pop(task_id, None)
