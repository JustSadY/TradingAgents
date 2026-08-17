from __future__ import annotations

from backend.core import task_store

from .models import AnalysisTaskMeta


class RedisBackend:
    """Adapter around the existing Redis-backed task store.

    Keeping this adapter is intentional during the migration: Redis key names,
    fallback behavior and pub/sub stay in infrastructure while callers depend
    on the analysis-runtime contract.
    """

    async def register(self, meta: AnalysisTaskMeta) -> None:
        await task_store.set_meta(meta.task_id, meta.store_payload())
        await task_store.set_owner(meta.task_id, meta.user_id)

    async def metadata(self, task_id: str) -> AnalysisTaskMeta | None:
        payload = await task_store.get_meta(task_id)
        if payload is None:
            return None
        return AnalysisTaskMeta.from_store_payload(task_id, payload)

    async def set_owner(self, task_id: str, user_id: int | None) -> None:
        await task_store.set_owner(task_id, user_id)

    async def owner(self, task_id: str) -> int | None:
        return await task_store.get_owner(task_id)

    async def heartbeat(self, task_id: str, user_id: int | None = None) -> None:
        await task_store.touch_task(task_id, user_id)

    async def request_cancel(self, task_id: str) -> None:
        await task_store.request_cancel(task_id)

    async def is_cancelled(self, task_id: str) -> bool:
        return await task_store.is_cancel_requested(task_id)

    async def clear_cancel(self, task_id: str) -> None:
        await task_store.clear_cancel_request(task_id)

    async def clear_metadata(self, task_id: str, user_id: int | None = None) -> None:
        await task_store.clear_meta(task_id, user_id)

    async def clear_owner(self, task_id: str) -> None:
        await task_store.clear_owner(task_id)

    async def complete(self, task_id: str, user_id: int | None = None) -> None:
        await task_store.clear_meta(task_id, user_id)
        await task_store.clear_owner(task_id)
        await task_store.clear_cancel_request(task_id)

    async def active_tasks(self, user_id: int) -> list[AnalysisTaskMeta]:
        rows = await task_store.list_tasks_for_user(user_id)
        return [
            AnalysisTaskMeta.from_store_payload(
                str(row["task_id"]),
                {key: value for key, value in row.items() if key != "task_id"},
            )
            for row in rows
        ]

    async def publish_cancel(self, task_id: str) -> None:
        await task_store.publish_cancel(task_id)
