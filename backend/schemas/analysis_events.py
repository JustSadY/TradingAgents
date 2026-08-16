"""The event vocabulary of the analysis progress WebSocket.

This is the one boundary the rest of the API's typing work does not reach:
`/ws/analysis/{task_id}` carries a stream of JSON events that appear in no
OpenAPI path, so the browser had a hand-written mirror of the payload and an
if/else chain over `event.type`, with nothing checking either against what the
backend actually sends.

`stall_warning` is what that gap costs. It is emitted when an analysis goes
silent for longer than the user's configured `stall_timeout_seconds`, and the
browser had no branch for it — so the setting existed, the detection worked,
and the user saw "Progress: heartbeat".

The union below is the source of truth. It is published through `/api/meta`,
which means the generated TypeScript client carries it and a frontend test can
assert the client handles every member. Adding an event type here without
handling it in the browser fails that test.
"""

from typing import Literal, get_args

AnalysisEventType = Literal[
    # Lifecycle
    "status",
    "progress",
    "complete",
    "error",
    # Content produced by the graph
    "report",
    "token",
    "mental_model",
    "debate_bubble",
    "decision",
    "risk_metrics",
    "stats",
    # Post-analysis execution, deliberately distinct from `complete`
    "order_result",
    # Resilience telemetry
    "retry",
    "fallback",
    "node_error",
    "circuit_open",
    "stall_warning",
]

ANALYSIS_EVENT_TYPES: tuple[str, ...] = get_args(AnalysisEventType)
