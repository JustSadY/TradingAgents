from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from backend.services.analysis.activity import AnalysisActivityTracker
from backend.services.analysis.emitter import AnalysisEmitter
from backend.services.stats_handler import StatsCallbackHandler

_logger = logging.getLogger(__name__)


class TokenStreamingCallbackHandler(AsyncCallbackHandler):
    """Callback handler that streams generated tokens, tool durations, and run stats to WebSocket."""

    def __init__(self, emitter: AnalysisEmitter, activity_tracker: AnalysisActivityTracker | None = None) -> None:
        self.emitter = emitter
        self._activity_tracker = activity_tracker
        self._tool_starts: dict[UUID, float] = {}
        self._stats_handler = StatsCallbackHandler()

    @property
    def llm_calls(self) -> int:
        return self._stats_handler.llm_calls

    @property
    def tokens_in(self) -> int:
        return self._stats_handler.tokens_in

    @property
    def tokens_out(self) -> int:
        return self._stats_handler.tokens_out

    async def _emit_stats(self) -> None:
        try:
            await self.emitter.emit(
                {
                    "type": "stats",
                    "llm_calls": self.llm_calls,
                    "tokens_in": self.tokens_in,
                    "tokens_out": self.tokens_out,
                }
            )
        except Exception as e:
            _logger.debug("Failed to emit live stats: %s", e)

    def _mark_activity(self) -> None:
        """Refresh this run's liveness clock without letting telemetry fail it."""
        if self._activity_tracker is None:
            return
        try:
            self._activity_tracker.touch()
        except Exception as exc:  # noqa: BLE001 — liveness telemetry is best-effort
            _logger.debug("Failed to refresh analysis activity: %s", exc)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._mark_activity()
        self._stats_handler.on_chat_model_start(
            serialized, messages, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )
        await self._emit_stats()

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._mark_activity()
        self._stats_handler.on_llm_start(
            serialized, prompts, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )
        await self._emit_stats()

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._mark_activity()
        self._stats_handler.on_llm_end(
            response, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )
        await self._emit_stats()

    async def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Stream token-by-token update via the WebSocket emitter."""
        self._mark_activity()
        agent_name = None
        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
        elif tags:
            agent_name = tags[0]

        if not agent_name:
            agent_name = "thinking"

        try:
            await self.emitter.emit(
                {
                    "type": "token",
                    "agent": agent_name,
                    "token": token,
                }
            )
        except Exception as e:
            _logger.debug("Failed to emit token: %s", e)

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Stream progress when a tool starts execution."""
        self._mark_activity()
        self._tool_starts[run_id] = time.time()
        self._stats_handler.on_tool_start(
            serialized, input_str, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )
        agent_name = None
        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
        elif tags:
            agent_name = tags[0]

        if agent_name:
            try:
                from backend.core.catalog import node_progress

                prog = node_progress(f"{agent_name}_tools")
                if prog:
                    await self.emitter.emit(prog)
            except Exception as e:
                _logger.debug("Failed to emit tool progress: %s", e)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._mark_activity()
        self._tool_starts.pop(run_id, None)
        self._stats_handler.on_tool_error(
            error, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Stream progress when a tool completes execution, including duration."""
        self._mark_activity()
        start_time = self._tool_starts.pop(run_id, None)
        duration_str = ""
        if start_time:
            duration = time.time() - start_time
            duration_str = f" (took {duration:.1f}s)"

        agent_name = None
        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
        elif tags:
            agent_name = tags[0]

        if agent_name:
            try:
                from backend.core.catalog import node_progress

                prog = node_progress(f"{agent_name}_tools")
                if prog:
                    label = f"{prog['label']}{duration_str}"
                    await self.emitter.emit(
                        {
                            "type": "progress",
                            "node": prog["node"],
                            "label": label,
                            "stage": prog["stage"],
                        }
                    )
            except Exception as e:
                _logger.debug("Failed to emit tool end progress: %s", e)
