"""Prometheus metric definitions and renderer.

All metrics live on the default registry. This module only depends on
prometheus_client, so it is safe to import from any layer (including the
trading_agents engine).
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

ANALYSIS_RUNS = Counter(
    "tradingagents_analysis_runs_total",
    "Analysis runs by final status.",
    ["status"],
)

ANALYSIS_DURATION = Histogram(
    "tradingagents_analysis_duration_seconds",
    "Wall-clock duration of successfully completed analysis runs.",
    buckets=(15, 30, 60, 90, 120, 180, 240, 300, 420, 600),
)

NODE_DURATION = Histogram(
    "tradingagents_node_duration_seconds",
    "Duration of guarded graph node executions, retries included.",
    ["node", "kind"],
    buckets=(1, 2.5, 5, 10, 20, 30, 60, 90, 120, 180),
)

NODE_RETRIES = Counter(
    "tradingagents_node_retries_total",
    "Retries performed by guarded engine calls.",
    ["label"],
)

NODE_ERRORS = Counter(
    "tradingagents_node_errors_total",
    "Guarded node executions that exhausted their retries.",
    ["node", "kind"],
)

NODE_ERRORS_BY_TYPE = Counter(
    "tradingagents_node_errors_by_type_total",
    "Guarded node errors classified by error category.",
    ["node", "kind", "error_type"],
)

TOOL_ERRORS = Counter(
    "tradingagents_tool_errors_total",
    "Tool execution errors classified by error category.",
    ["tool_name", "error_type"],
)

NODE_FALLBACKS = Counter(
    "tradingagents_node_fallbacks_total",
    "Failed nodes replaced by their fallback stub.",
    ["node", "kind"],
)

NODE_CIRCUIT_OPEN = Counter(
    "tradingagents_node_circuit_open_total",
    "Times a node was short-circuited by the circuit breaker.",
    ["node", "kind"],
)

WS_CONNECTIONS = Gauge(
    "tradingagents_websocket_connections",
    "Currently connected analysis WebSocket clients.",
)

SIGNAL_PARSE_FALLBACK = Counter(
    "tradingagents_signal_parse_fallback_total",
    "Final signals that defaulted because no rating could be parsed from the decision text.",
)

AUTO_ORDER_SKIPPED = Counter(
    "tradingagents_auto_order_skipped_total",
    "Auto-orders skipped by a guardrail instead of being placed.",
    ["reason"],
)

def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
