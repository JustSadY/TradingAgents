"""Response contracts for the token-usage and system-health panels.

These endpoints returned ``dict[str, Any]``, so OpenAPI described them as
free-form objects and the frontend kept its own copy of each shape behind a
cast. Declaring them here means the generated client is the only description
of the payload.
"""

from pydantic import BaseModel

from backend.core.model_pricing import PricingSource
from backend.schemas.common import ApiResponse


class TokenUsageBreakdown(BaseModel):
    """Cost and volume for one provider/model pair."""

    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    analyses: int
    estimated_cost_usd: float | None
    pricing_source: PricingSource
    pricing_is_fallback: bool


class TokenUsageDay(BaseModel):
    day: str
    tokens_in: int
    tokens_out: int
    analyses: int


class TokenUsageRead(BaseModel):
    total_tokens_in: int
    total_tokens_out: int
    total_tokens: int
    total_cost_usd: float | None
    breakdown: list[TokenUsageBreakdown]
    daily: list[TokenUsageDay]


class AnalysisDurationMetrics(ApiResponse):
    count: int = 0
    sum_seconds: float = 0.0
    avg_seconds: float = 0.0


class SystemMetricsRead(ApiResponse):
    """Key Prometheus counters, flattened for the admin dashboard.

    Every field carries a default because the collector returns only ``error``
    when ``prometheus_client`` cannot be imported.
    """

    analysis_runs: dict[str, int] = {}
    analysis_duration: AnalysisDurationMetrics = AnalysisDurationMetrics()
    node_errors: dict[str, int] = {}
    node_fallbacks: dict[str, int] = {}
    node_retries: int = 0
    websocket_connections: int = 0
    signal_parse_fallbacks: int = 0
    auto_order_skipped: dict[str, int] = {}
    total_runs: int = 0
    error_rate_pct: float = 0.0
    error: str | None = None


class QualityConfidenceCounts(ApiResponse):
    high: int = 0
    medium: int = 0
    low: int = 0


class RunQualitySummary(ApiResponse):
    period_days: int
    total_runs: int
    #: Completed runs with no usable quality assessment, counted rather than
    #: averaged so a spike in them is visible instead of hidden.
    unknown: int
    confidence_counts: QualityConfidenceCounts
    avg_score: float | None = None


class SystemHealthRead(BaseModel):
    signal_parse_fallbacks: int
    auto_order_skipped: dict[str, int]
    quality: RunQualitySummary
