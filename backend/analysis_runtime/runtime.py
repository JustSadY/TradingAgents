from __future__ import annotations

from typing import Any

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

    async def owner(self, task_id: str) -> int | None:
        return await self.backend.owner(task_id)

    async def heartbeat(self, task_id: str, user_id: int | None = None) -> None:
        await self.backend.heartbeat(task_id, user_id)

    async def request_cancel(self, task_id: str) -> None:
        await self.backend.request_cancel(task_id)

    async def is_cancelled(self, task_id: str) -> bool:
        # Route through the compatibility method while the existing regression
        # suite still monkeypatches ``is_cancel_requested`` on the facade.
        return await self.is_cancel_requested(task_id)

    async def complete(self, task_id: str, user_id: int | None = None) -> None:
        await self.backend.complete(task_id, user_id)

    async def active_tasks(self, user_id: int) -> list[AnalysisTaskMeta]:
        return await self.backend.active_tasks(user_id)

    async def publish_cancel(self, task_id: str) -> None:
        await self.backend.publish_cancel(task_id)

    # Compatibility surface for the current facade. These methods let the
    # migration remove Redis/task_store imports first without changing every
    # local-registry call in the same commit. New code should use the typed API.
    async def set_owner(self, task_id: str, user_id: int | None) -> None:
        await self.backend.set_owner(task_id, user_id)

    async def get_owner(self, task_id: str) -> int | None:
        return await self.owner(task_id)

    async def clear_owner(self, task_id: str) -> None:
        await self.backend.clear_owner(task_id)

    async def set_meta(self, task_id: str, payload: dict[str, Any]) -> None:
        await self.register(AnalysisTaskMeta.from_store_payload(task_id, payload))

    async def get_meta(self, task_id: str) -> dict[str, Any] | None:
        meta = await self.metadata(task_id)
        return None if meta is None else meta.store_payload()

    async def touch_task(self, task_id: str, user_id: int | None = None) -> None:
        await self.heartbeat(task_id, user_id)

    async def clear_meta(self, task_id: str, user_id: int | None = None) -> None:
        await self.backend.clear_metadata(task_id, user_id)

    async def is_cancel_requested(self, task_id: str) -> bool:
        return await self.backend.is_cancelled(task_id)

    async def clear_cancel_request(self, task_id: str) -> None:
        await self.backend.clear_cancel(task_id)

    async def list_tasks_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return [{"task_id": meta.task_id, **meta.store_payload()} for meta in await self.active_tasks(user_id)]
