from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from backend.core.event_bus import publish_close, publish_event


class AnalysisEmitter:
    """Handles real-time event emission for analysis tasks."""

    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop | None = None):
        self.task_id = task_id
        self.loop = loop or asyncio.get_running_loop()
        self.terminal_event_emitted = False
        # Imperative debate loops can publish a turn before their enclosing
        # LangGraph node returns. The normal graph observer later sees that
        # same turn once. Keep a one-use suppression token for that replay so
        # the UI gets exactly one bubble without globally deduping legitimate
        # later turns that happen to contain identical text.
        self._debate_replay_suppressions: Counter[tuple[str, str, str]] = Counter()

    async def emit(self, event: dict[str, Any]) -> None:
        """Send an event to the task's WebSocket subscribers (direct or via Redis)."""
        await publish_event(self.task_id, event)

    def emit_threadsafe(self, event: dict[str, Any]) -> None:
        """Send an event safely from outside the main async loop."""
        asyncio.run_coroutine_threadsafe(self.emit(event), self.loop)

    async def emit_status(self, agent: str, status: str = "starting", message: str | None = None) -> None:
        """Emit a structured status update.

        ``agent`` is the producer identifier, while ``status`` is a compact
        lifecycle state. Human-readable progress belongs in ``message`` so
        consumers do not have to overload the agent field to display it.
        """
        event: dict[str, Any] = {"type": "status", "status": status, "agent": agent}
        if message:
            event["message"] = message
        await self.emit(event)

    async def emit_progress(self, label: str, stage: str, node: str) -> None:
        await self.emit({"type": "progress", "label": label, "stage": stage, "node": node})

    async def emit_report(self, section: str, content: str) -> None:
        await self.emit({"type": "report", "section": section, "content": content})

    async def emit_debate_bubble(
        self,
        debate_type: str,
        message: str,
        *,
        sender: str | None = None,
        content: str | None = None,
        expect_graph_replay: bool = False,
    ) -> None:
        """Emit one complete debate turn.

        ``message`` remains for older clients. New clients consume the
        structured sender/content fields, which avoids reparsing multiline
        Markdown responses on the browser side.

        ``expect_graph_replay`` is used only by imperative inner debate loops:
        the turn is emitted immediately and one later graph-observer emission
        of the exact same structured turn is suppressed. This is intentionally
        a counter, not a permanent content set, so identical arguments in a
        genuinely later round remain visible.
        """
        replay_key = (debate_type, sender or "", content if content is not None else message)
        if expect_graph_replay:
            self._debate_replay_suppressions[replay_key] += 1
        elif self._debate_replay_suppressions.get(replay_key, 0) > 0:
            self._debate_replay_suppressions[replay_key] -= 1
            if self._debate_replay_suppressions[replay_key] <= 0:
                self._debate_replay_suppressions.pop(replay_key, None)
            return

        event: dict[str, Any] = {"type": "debate_bubble", "debate_type": debate_type, "message": message}
        if sender:
            event["sender"] = sender
        if content is not None:
            event["content"] = content
        await self.emit(event)

    async def emit_mental_model(self, agent: str, thought: str) -> None:
        """Send a mental model (thought process) event for an agent."""
        await self.emit({"type": "mental_model", "agent": agent, "thought": thought})

    async def emit_decision(self, signal: str | None, final_decision: str) -> None:
        await self.emit({"type": "decision", "signal": signal, "final_decision": final_decision})

    async def emit_order_result(
        self,
        *,
        analysis_id: int,
        ticker: str,
        action: str | None,
        signal: str | None,
        outcome: str,
        broker_status: str | None = None,
        order_id: str | None = None,
        filled_quantity: object | None = None,
        filled_price: object | None = None,
        commission: object | None = None,
        message: str = "",
        reason_code: str | None = None,
    ) -> None:
        """Publish the durable outcome of an optional post-analysis order.

        ``complete`` means that the AI report was persisted; it must not be
        interpreted as an assertion that an order was filled. This separate
        event gives the client an explicit filled/partially-filled/skipped/
        rejected/error or reconciliation-required result while retaining
        broker-specific detail for order history. Values may be ``Decimal``
        instances, so convert them at this wire boundary instead of relying on
        a JSON encoder implementation.
        """

        def _number(value: object | None) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        filled_quantity_number = _number(filled_quantity)
        normalized_broker_status = (broker_status or "").strip().upper()
        if normalized_broker_status == "RECONCILIATION_REQUIRED":
            # A broker request may have escaped the local transaction even when
            # its exact fill/audit state is unknown. Calling that "rejected"
            # invites an unsafe retry; expose the operational state explicitly.
            outcome = "reconciliation_required"
        elif normalized_broker_status == "PARTIALLY_FILLED" or (
            normalized_broker_status in {"CANCELED", "EXPIRED"}
            and filled_quantity_number is not None
            and filled_quantity_number > 0
        ):
            # Alpaca can report a terminal cancellation after part of the order
            # already executed. Treating that as a rejection hides a real
            # position change and can make a retry dangerously duplicate size.
            outcome = "partially_filled"

        if outcome not in {
            "filled",
            "partially_filled",
            "skipped",
            "rejected",
            "error",
            "reconciliation_required",
        }:
            raise ValueError(f"Unsupported order outcome: {outcome}")

        event: dict[str, Any] = {
            "type": "order_result",
            "analysis_id": analysis_id,
            "ticker": ticker,
            "action": action,
            "signal": signal,
            "status": outcome,
            "outcome": outcome,
            "broker_status": broker_status,
            "order_id": order_id or None,
            "filled_quantity": filled_quantity_number,
            "filled_price": _number(filled_price),
            "commission": _number(commission),
            "message": message,
        }
        if reason_code:
            event["reason_code"] = reason_code
        await self.emit(event)

    async def emit_complete(
        self,
        analysis_id: int,
        signal: str | None,
        duration_seconds: float,
        llm_calls: int,
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
        self.terminal_event_emitted = True

    async def emit_error(self, message: str) -> None:
        await self.emit({"type": "error", "message": message})
        self.terminal_event_emitted = True

    async def emit_retry(self, node: str, attempt: int, max_attempts: int, error: str) -> None:
        await self.emit(
            {
                "type": "retry",
                "node": node,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error,
            }
        )

    async def emit_fallback(self, node: str, kind: str, error: str) -> None:
        await self.emit(
            {
                "type": "fallback",
                "node": node,
                "kind": kind,
                "error": error,
            }
        )

    async def emit_node_error(self, node: str, kind: str, error: str, error_type: str) -> None:
        await self.emit(
            {
                "type": "node_error",
                "node": node,
                "kind": kind,
                "error": error,
                "error_type": error_type,
            }
        )

    async def emit_circuit_open(self, node: str, kind: str, elapsed_seconds: float) -> None:
        await self.emit(
            {
                "type": "circuit_open",
                "node": node,
                "kind": kind,
                "elapsed_seconds": round(elapsed_seconds, 1),
            }
        )

    async def close(self) -> None:
        await publish_close(self.task_id)
