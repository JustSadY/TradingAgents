from __future__ import annotations

import asyncio
from typing import Any

from backend.core.event_bus import publish_close, publish_event


class AnalysisEmitter:
    """Handles real-time event emission for analysis tasks."""

    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop | None = None):
        self.task_id = task_id
        self.loop = loop or asyncio.get_running_loop()

    async def emit(self, event: dict[str, Any]) -> None:
        """Send an event to the task's WebSocket subscribers (direct or via Redis)."""
        await publish_event(self.task_id, event)

    def emit_threadsafe(self, event: dict[str, Any]) -> None:
        """Send an event safely from outside the main async loop."""
        asyncio.run_coroutine_threadsafe(self.emit(event), self.loop)

    async def emit_status(self, agent: str, status: str = "starting") -> None:
        await self.emit({"type": "status", "status": status, "agent": agent})

    async def emit_progress(self, label: str, stage: str, node: str) -> None:
        await self.emit({"type": "progress", "label": label, "stage": stage, "node": node})

    async def emit_report(self, section: str, content: str) -> None:
        await self.emit({"type": "report", "section": section, "content": content})

    async def emit_debate_bubble(self, debate_type: str, message: str) -> None:
        await self.emit({"type": "debate_bubble", "debate_type": debate_type, "message": message})

    async def emit_mental_model(self, agent: str, thought: str) -> None:
        """Send a mental model (thought process) event for an agent."""
        await self.emit({"type": "mental_model", "agent": agent, "thought": thought})

    async def emit_decision(self, signal: str | None, final_decision: str) -> None:
        await self.emit({"type": "decision", "signal": signal, "final_decision": final_decision})

    async def emit_complete(
        self, analysis_id: int, signal: str | None, duration_seconds: float, llm_calls: int,
        estimated_cost_usd: float | None = None,
    ) -> None:
        await self.emit(
            {
                "type": "complete",
                "analysis_id": analysis_id,
                "signal": signal,
                "duration_seconds": round(duration_seconds, 2),
                "llm_calls": llm_calls,
                "estimated_cost_usd": estimated_cost_usd,
            }
        )

    async def emit_error(self, message: str) -> None:
        await self.emit({"type": "error", "message": message})

    async def emit_retry(self, node: str, attempt: int, max_attempts: int, error: str) -> None:
        await self.emit({
            "type": "retry",
            "node": node,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "error": error,
        })

    async def emit_fallback(self, node: str, kind: str, error: str) -> None:
        await self.emit({
            "type": "fallback",
            "node": node,
            "kind": kind,
            "error": error,
        })

    async def emit_node_error(self, node: str, kind: str, error: str, error_type: str) -> None:
        await self.emit({
            "type": "node_error",
            "node": node,
            "kind": kind,
            "error": error,
            "error_type": error_type,
        })

    async def emit_circuit_open(self, node: str, kind: str, elapsed_seconds: float) -> None:
        await self.emit({
            "type": "circuit_open",
            "node": node,
            "kind": kind,
            "elapsed_seconds": round(elapsed_seconds, 1),
        })

    async def close(self) -> None:
        await publish_close(self.task_id)
