from __future__ import annotations

from typing import Any, Protocol


class AnalysisEventTransport(Protocol):
    async def publish(self, task_id: str, event: dict[str, Any]) -> None: ...

    async def close(self, task_id: str) -> None: ...


class CoreEventBusTransport:
    """Infrastructure adapter for the existing local/Redis analysis event bus."""

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        from backend.core.event_bus import publish_event

        await publish_event(task_id, event)

    async def close(self, task_id: str) -> None:
        from backend.core.event_bus import publish_close

        await publish_close(task_id)


class AnalysisEventStream:
    """Business-facing event publication boundary for analysis tasks."""

    def __init__(self, transport: AnalysisEventTransport) -> None:
        self.transport = transport

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        await self.transport.publish(task_id, event)

    async def close(self, task_id: str) -> None:
        await self.transport.close(task_id)


_event_stream = AnalysisEventStream(CoreEventBusTransport())


def get_analysis_event_stream() -> AnalysisEventStream:
    return _event_stream
