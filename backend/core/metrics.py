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

NODE_FALLBACKS = Counter(
    "tradingagents_node_fallbacks_total",
    "Failed nodes replaced by their fallback stub.",
    ["node", "kind"],
)

WS_CONNECTIONS = Gauge(
    "tradingagents_websocket_connections",
    "Currently connected analysis WebSocket clients.",
)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
