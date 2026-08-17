from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class AnalysisTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisTaskMeta(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    asset_type: str
    user_id: int | None
    status: AnalysisTaskStatus
    started_at: float

    def store_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"task_id"})

    @classmethod
    def from_store_payload(cls, task_id: str, payload: dict[str, Any]) -> "AnalysisTaskMeta":
        return cls(task_id=task_id, **payload)


class AnalysisEventEnvelope(BaseModel):
    version: Literal[1] = 1
    event_id: str
    task_id: str
    sequence: int
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TerminalResult:
    status: AnalysisTaskStatus
    reason: str | None = None
