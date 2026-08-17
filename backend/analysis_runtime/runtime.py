from __future__ import annotations

from .backend import AnalysisRuntimeBackend
from .models import AnalysisTaskMeta


class AnalysisRuntime:
    """Business-facing facade for shared analysis task state."""

    def __init__(self, backend: AnalysisRuntimeBackend) -> None:
        self.backend = backend

    async def register(self, meta: AnalysisTaskMeta) -> None:
        await self.backend.register(meta)

    async def metadata(self, task_id: str) -> AnalysisTaskMeta | None:
        return await self.backend.metadata(task_id)

    async def set_owner(self, task_id: str, user_id: int | None) -> None:
        await self.backend.set_owner(task_id, user_id)

    async def owner(self, task_id: str) -> int | None:
        return await self.backend.owner(task_id)

    async def clear_owner(self, task_id: str) -> None:
        await self.backend.clear_owner(task_id)

    async def heartbeat(self, task_id: str, user_id: int | None = None) -> None:
        await self.backend.heartbeat(task_id, user_id)

    async def request_cancel(self, task_id: str) -> None:
        await self.backend.request_cancel(task_id)

    async def is_cancelled(self, task_id: str) -> bool:
        return await self.backend.is_cancelled(task_id)

    async def complete(self, task_id: str, user_id: int | None = None) -> None:
        await self.backend.complete(task_id, user_id)

    async def active_tasks(self, user_id: int) -> list[AnalysisTaskMeta]:
        return await self.backend.active_tasks(user_id)

    async def publish_cancel(self, task_id: str) -> None:
        await self.backend.publish_cancel(task_id)
