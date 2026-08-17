from __future__ import annotations

from pathlib import Path

import backend.app.lifespan as app_lifespan
import backend.worker as worker


_FORBIDDEN = (
    "backend.core.event_bus",
    "backend.core.task_store",
    "backend.core.redis_bus",
)


def _source(module) -> str:
    return Path(module.__file__).read_text()


def test_web_lifespan_uses_analysis_runtime_for_distributed_transport():
    source = _source(app_lifespan)

    for name in _FORBIDDEN:
        assert name not in source
    assert "analysis_distributed.forward_events" in source
    assert "analysis_distributed.listen_for_controls" in source
    assert "analysis_distributed.close" in source


def test_worker_uses_analysis_runtime_for_distributed_transport():
    source = _source(worker)

    for name in _FORBIDDEN:
        assert name not in source
    assert "analysis_distributed.listen_for_controls" in source
    assert "analysis_distributed.close" in source
