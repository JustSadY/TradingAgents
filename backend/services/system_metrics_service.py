"""Collect key TradingAgents Prometheus metrics as JSON for the admin dashboard.

Extracted from ``api/token_analytics.py`` so the route handler stays thin: all
registry traversal and aggregation lives here.
"""

from __future__ import annotations

from typing import Any


def _total_samples(metric) -> list:
    """Samples of a metric whose name ends in ``_total`` (the counter values)."""
    return [s for s in metric.samples if s.name.endswith("_total")]

def _labeled_totals(metric, label: str) -> dict[str, int]:
    """Sum ``_total`` samples grouped by the value of ``label``."""
    out: dict[str, int] = {}
    for s in _total_samples(metric):
        key = s.labels.get(label, "unknown")
        out[key] = out.get(key, 0) + int(s.value)
    return out

def _read_duration(metric) -> dict[str, float]:
    """Extract count/sum from a histogram metric's ``_count``/``_sum`` samples."""
    duration = {"count": 0, "sum_seconds": 0.0, "avg_seconds": 0.0}
    for sample in metric.samples:
        if sample.name.endswith("_count"):
            duration["count"] = int(sample.value)
        elif sample.name.endswith("_sum"):
            duration["sum_seconds"] = round(sample.value, 2)
    return duration

def collect_system_metrics() -> dict[str, Any]:
    """Return key TradingAgents Prometheus metrics as JSON for the admin dashboard."""
    try:
        from prometheus_client import REGISTRY
    except ImportError:
        return {"error": "prometheus_client not available"}

    result: dict[str, Any] = {
        "analysis_runs": {},
        "analysis_duration": {"count": 0, "sum_seconds": 0.0, "avg_seconds": 0.0},
        "node_errors": {},
        "node_fallbacks": {},
        "node_retries": 0,
        "websocket_connections": 0,
        "signal_parse_fallbacks": 0,
        "auto_order_skipped": {},
    }

    for metric in REGISTRY.collect():
        name = metric.name
        if name == "tradingagents_analysis_runs_total":
            result["analysis_runs"] = _labeled_totals(metric, "status")
        elif name == "tradingagents_analysis_duration_seconds":
            result["analysis_duration"] = _read_duration(metric)
        elif name == "tradingagents_node_errors_total":
            result["node_errors"] = _labeled_totals(metric, "node")
        elif name == "tradingagents_node_fallbacks_total":
            result["node_fallbacks"] = _labeled_totals(metric, "node")
        elif name == "tradingagents_node_retries_total":
            result["node_retries"] = sum(int(s.value) for s in _total_samples(metric))
        elif name == "tradingagents_signal_parse_fallback_total":
            result["signal_parse_fallbacks"] = sum(int(s.value) for s in _total_samples(metric))
        elif name == "tradingagents_auto_order_skipped_total":
            result["auto_order_skipped"] = _labeled_totals(metric, "reason")
        elif name == "tradingagents_websocket_connections":
            for sample in metric.samples:
                result["websocket_connections"] = int(sample.value)

    total_runs = sum(result["analysis_runs"].values())
    result["total_runs"] = total_runs

    dur = result["analysis_duration"]
    if dur["count"] > 0:
        dur["avg_seconds"] = round(dur["sum_seconds"] / dur["count"], 1)

    total_errors = sum(result["node_errors"].values())
    result["error_rate_pct"] = round(total_errors / total_runs * 100, 1) if total_runs else 0.0

    return result
