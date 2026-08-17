from __future__ import annotations

from .local_backend import LocalBackend
from .models import AnalysisEventEnvelope, AnalysisTaskMeta, AnalysisTaskStatus, TerminalResult
from .redis_backend import RedisBackend
from .runtime import AnalysisRuntime

_runtime = AnalysisRuntime(RedisBackend())


def get_analysis_runtime() -> AnalysisRuntime:
    return _runtime


__all__ = [
    "AnalysisEventEnvelope",
    "AnalysisRuntime",
    "AnalysisTaskMeta",
    "AnalysisTaskStatus",
    "LocalBackend",
    "RedisBackend",
    "TerminalResult",
    "get_analysis_runtime",
]
