from __future__ import annotations
import asyncio
from typing import Any
from backend.core.websocket import ws_manager

class AnalysisEmitter:
    """Handles real-time event emission for analysis tasks."""
    
    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop | None = None):
        self.task_id = task_id
        self.loop = loop or asyncio.get_running_loop()

    async def emit(self, event: dict[str, Any]) -> None:
        """Send an event to the task's WebSocket connections."""
        await ws_manager.send(self.task_id, event)

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

    async def emit_decision(self, signal: str | None, final_decision: str) -> None:
        await self.emit({"type": "decision", "signal": signal, "final_decision": final_decision})

    async def emit_complete(self, analysis_id: int, signal: str | None, duration_seconds: float, llm_calls: int) -> None:
        await self.emit({
            "type": "complete",
            "analysis_id": analysis_id,
            "signal": signal,
            "duration_seconds": round(duration_seconds, 2),
            "llm_calls": llm_calls,
        })

    async def emit_error(self, message: str) -> None:
        await self.emit({"type": "error", "message": message})

    async def close(self) -> None:
        await ws_manager.close_task(self.task_id)
