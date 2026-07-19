from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Coroutine

_logger = logging.getLogger(__name__)


class BackgroundTaskTracker:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def track(self, coro: Awaitable[None] | Coroutine) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def cancel_all(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    @property
    def active_count(self) -> int:
        return len(self._tasks)


class ScopedBackgroundTaskTracker(BackgroundTaskTracker):
    def __init__(self) -> None:
        super().__init__()
        self._scoped: dict[str, set[asyncio.Task]] = {}

    def track(self, coro: Awaitable[None] | Coroutine, scope: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        if scope:
            self._scoped.setdefault(scope, set()).add(task)

        def _cleanup(done_task: asyncio.Task) -> None:
            self._tasks.discard(done_task)
            if scope and scope in self._scoped:
                scoped_set = self._scoped[scope]
                scoped_set.discard(done_task)
                if not scoped_set:
                    self._scoped.pop(scope, None)

        task.add_done_callback(_cleanup)
        return task

    def gather_scope(self, scope: str) -> list[asyncio.Task]:
        return list(self._scoped.get(scope, set()))

    async def await_scope(self, scope: str) -> None:
        pending = self.gather_scope(scope)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
