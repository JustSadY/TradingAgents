from __future__ import annotations

from .event_stream import AnalysisEventStream, AnalysisEventTransport, CoreEventBusTransport, get_analysis_event_stream
from .local_backend import LocalBackend
from .models import AnalysisEventEnvelope, AnalysisTaskMeta, AnalysisTaskStatus, TerminalResult
from .redis_backend import RedisBackend
from .runtime import AnalysisRuntime

_runtime = AnalysisRuntime(RedisBackend())


def get_analysis_runtime() -> AnalysisRuntime:
    return _runtime


__all__ = [
    "AnalysisEventEnvelope",
    "AnalysisEventStream",
    "AnalysisEventTransport",
    "AnalysisRuntime",
    "AnalysisTaskMeta",
    "AnalysisTaskStatus",
    "CoreEventBusTransport",
    "LocalBackend",
    "RedisBackend",
    "TerminalResult",
    "get_analysis_event_stream",
    "get_analysis_runtime",
]
