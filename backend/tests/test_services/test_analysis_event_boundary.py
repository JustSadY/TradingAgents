from __future__ import annotations

from pathlib import Path

from backend.analysis_runtime.event_stream import AnalysisEventStream
from backend.services.analysis import emitter as emitter_module


async def test_event_stream_delegates_publish_and_close():
    calls: list[tuple[str, object]] = []

    class Transport:
        async def publish(self, task_id: str, event: dict) -> None:
            calls.append(("publish", (task_id, event)))

        async def close(self, task_id: str) -> None:
            calls.append(("close", task_id))

    stream = AnalysisEventStream(Transport())

    await stream.publish("task-1", {"type": "progress", "stage": "running"})
    await stream.close("task-1")

    assert calls == [
        ("publish", ("task-1", {"type": "progress", "stage": "running"})),
        ("close", "task-1"),
    ]


def test_analysis_emitter_does_not_import_core_event_transport_directly():
    source = Path(emitter_module.__file__).read_text()

    assert "backend.core.event_bus" not in source
    assert "backend.core.redis_bus" not in source
    assert "backend.core.websocket" not in source
    assert "get_analysis_event_stream" in source
