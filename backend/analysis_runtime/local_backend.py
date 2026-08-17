from __future__ import annotations

from .models import AnalysisTaskMeta


class LocalBackend:
    """In-process implementation of the analysis runtime backend contract."""

    def __init__(self) -> None:
        self._meta: dict[str, AnalysisTaskMeta] = {}
        self._owners: dict[str, int | None] = {}
        self._cancelled: set[str] = set()

    async def register(self, meta: AnalysisTaskMeta) -> None:
        self._meta[meta.task_id] = meta
        self._owners[meta.task_id] = meta.user_id

    async def metadata(self, task_id: str) -> AnalysisTaskMeta | None:
        return self._meta.get(task_id)

    async def set_owner(self, task_id: str, user_id: int | None) -> None:
        self._owners[task_id] = user_id

    async def owner(self, task_id: str) -> int | None:
        return self._owners.get(task_id)

    async def heartbeat(self, task_id: str, user_id: int | None = None) -> None:
        return None

    async def request_cancel(self, task_id: str) -> None:
        self._cancelled.add(task_id)

    async def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled

    async def clear_cancel(self, task_id: str) -> None:
        self._cancelled.discard(task_id)

    async def clear_metadata(self, task_id: str, user_id: int | None = None) -> None:
        self._meta.pop(task_id, None)

    async def clear_owner(self, task_id: str) -> None:
        self._owners.pop(task_id, None)

    async def complete(self, task_id: str, user_id: int | None = None) -> None:
        self._meta.pop(task_id, None)
        self._owners.pop(task_id, None)
        self._cancelled.discard(task_id)

    async def active_tasks(self, user_id: int) -> list[AnalysisTaskMeta]:
        return [meta for meta in self._meta.values() if meta.user_id == user_id]

    async def publish_cancel(self, task_id: str) -> None:
        return None
