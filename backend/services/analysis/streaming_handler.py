from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from backend.services.analysis.emitter import AnalysisEmitter

_logger = logging.getLogger(__name__)


class TokenStreamingCallbackHandler(AsyncCallbackHandler):
    """Callback handler that streams generated tokens, tool durations, and run stats to WebSocket."""

    def __init__(self, emitter: AnalysisEmitter) -> None:
        self.emitter = emitter
        self._tool_starts: dict[UUID, float] = {}
        self.llm_calls = 0
        self._run_usage: dict[UUID, dict[str, int]] = {}
        self._seen_runs: set[UUID] = set()

    @property
    def tokens_in(self) -> int:
        return sum(u["input"] for u in self._run_usage.values())

    @property
    def tokens_out(self) -> int:
        return sum(u["output"] for u in self._run_usage.values())

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
        if run_id not in self._seen_runs:
            self._seen_runs.add(run_id)
            self.llm_calls += 1
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
        await self.on_chat_model_start({}, [], run_id=run_id)

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
        from backend.services.stats_handler import StatsCallbackHandler

        usage = StatsCallbackHandler._extract_usage(response)
        if usage:
            self._run_usage[run_id] = usage
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
            # Prevent token streaming errors from interrupting model execution
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
        self._tool_starts[run_id] = time.time()
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
                    # Update label to include duration
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
