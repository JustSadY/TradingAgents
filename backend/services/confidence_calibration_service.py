"""Point-in-time confidence calibration for Portfolio Manager proposals.

LLM confidence is useful as a ranking signal, but it is not a probability
until it is checked against resolved outcomes.  This module deliberately uses
a small Bayesian/shrinkage calibrator rather than an unconstrained curve: the
per-user/rating samples available to a trading assistant are usually sparse.

The returned context is built before the graph starts.  The graph therefore
does not need a database session and historical runs can pass an empty context
without leaking future outcomes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_RISK_CLASSES = {
    "Buy": "long",
    "Overweight": "long",
    "Sell": "short",
    "Underweight": "short",
    "Hold": "flat",
}
_DEFAULT_PRIOR_MEAN = 0.5
_DEFAULT_PRIOR_STRENGTH = 8.0
_MAX_DIRECT_WEIGHT = 0.8


def rating_risk_class(rating: object) -> str:
    """Return a stable coarse decision class for sparse-sample pooling."""
    return _RISK_CLASSES.get(str(rating or "").strip(), "unknown")


def _decision_mapping(row: object) -> dict[str, Any]:
    raw = getattr(row, "portfolio_decision_json", None)
    if isinstance(raw, dict):
        return raw
    annotations = getattr(row, "chart_annotations", None)
    if isinstance(annotations, dict):
        nested = annotations.get("portfolio_decision") or annotations.get("portfolio_decision_json")
        if isinstance(nested, dict):
            return nested
    return {}


def _finite_probability(value: object) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= probability <= 1.0:
        return probability
    return None


def _directional_success(alpha_return: object, rating: object) -> bool | None:
    try:
        alpha = float(alpha_return)
    except (TypeError, ValueError):
        return None
    risk_class = rating_risk_class(rating)
    if risk_class == "long":
        return alpha > 0.0
    if risk_class == "short":
        return alpha < 0.0
    if risk_class == "flat":
        return abs(alpha) <= 0.02
    return None


def _bucket(confidence: float) -> str:
    """Ten percentage-point calibration buckets, clamped at one."""
    lower = min(0.9, max(0.0, int(confidence * 10) / 10))
    upper = min(1.0, lower + 0.1)
    return f"{lower:.1f}-{upper:.1f}"


def build_calibration_context(rows: list[object]) -> dict[str, Any]:
    """Build a serializable, privacy-scoped calibration summary from rows.

    Inputs are normally resolved *learning eligible* analyses for one user.
    We store only aggregate successes/counts in graph config, never historical
    raw decisions or reflected text.
    """
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "successes": 0})
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "successes": 0})
    total = 0
    successes = 0

    for row in rows:
        decision = _decision_mapping(row)
        confidence = _finite_probability(decision.get("confidence_score"))
        rating = decision.get("rating") or getattr(row, "signal", None)
        outcome = _directional_success(getattr(row, "alpha_return", None), rating)
        if confidence is None or outcome is None:
            continue
        risk_class = rating_risk_class(rating)
        if risk_class == "unknown":
            continue
        stats[risk_class]["count"] += 1
        buckets[f"{risk_class}:{_bucket(confidence)}"]["count"] += 1
        total += 1
        if outcome:
            stats[risk_class]["successes"] += 1
            buckets[f"{risk_class}:{_bucket(confidence)}"]["successes"] += 1
            successes += 1

    return {
        "method": "beta_binomial_shrinkage_v1",
        "prior_mean": _DEFAULT_PRIOR_MEAN,
        "prior_strength": _DEFAULT_PRIOR_STRENGTH,
        "total_samples": total,
        "total_successes": successes,
        "by_risk_class": dict(stats),
        "by_bucket": dict(buckets),
    }


def _posterior_mean(successes: int, count: int, *, prior_mean: float, prior_strength: float) -> float:
    return (successes + prior_mean * prior_strength) / (count + prior_strength)


def calibrate_confidence(raw_confidence: object, rating: object, context: dict[str, Any] | None) -> dict[str, Any]:
    """Return a conservative calibrated probability and its audit metadata.

    A rating/bucket posterior gets most influence only after meaningful sample
    evidence exists.  Sparse histories retain more of the PM's raw score,
    preventing a two-trade streak from declaring a false 100% confidence.
    """
    raw = _finite_probability(raw_confidence)
    if raw is None:
        raw = _DEFAULT_PRIOR_MEAN
    context = context if isinstance(context, dict) else {}
    prior_mean = _finite_probability(context.get("prior_mean")) or _DEFAULT_PRIOR_MEAN
    try:
        prior_strength = max(1.0, float(context.get("prior_strength", _DEFAULT_PRIOR_STRENGTH)))
    except (TypeError, ValueError):
        prior_strength = _DEFAULT_PRIOR_STRENGTH

    risk_class = rating_risk_class(rating)
    by_class = context.get("by_risk_class") if isinstance(context.get("by_risk_class"), dict) else {}
    by_bucket = context.get("by_bucket") if isinstance(context.get("by_bucket"), dict) else {}
    class_stats = by_class.get(risk_class) if isinstance(by_class.get(risk_class), dict) else {}
    bucket_stats = by_bucket.get(f"{risk_class}:{_bucket(raw)}")
    if not isinstance(bucket_stats, dict):
        bucket_stats = {}

    def _count(data: dict[str, Any], key: str) -> int:
        try:
            return max(0, int(data.get(key, 0)))
        except (TypeError, ValueError):
            return 0

    class_count = _count(class_stats, "count")
    class_successes = min(class_count, _count(class_stats, "successes"))
    bucket_count = _count(bucket_stats, "count")
    bucket_successes = min(bucket_count, _count(bucket_stats, "successes"))
    total_samples = _count(context, "total_samples")
    total_successes = min(total_samples, _count(context, "total_successes"))

    # Prefer a confidence-neighbourhood posterior, fall back to decision-class,
    # then global samples.  This maintains a useful calibration signal even
    # before every class/bucket has independently matured.
    if bucket_count:
        count, successes, source = bucket_count, bucket_successes, "rating_confidence_bucket"
    elif class_count:
        count, successes, source = class_count, class_successes, "rating_class"
    else:
        count, successes, source = total_samples, total_successes, "global"

    if count <= 0:
        return {
            "raw_confidence": raw,
            "calibrated_confidence": raw,
            "sample_count": 0,
            "source": "raw_no_resolved_samples",
            "risk_class": risk_class,
        }

    posterior = _posterior_mean(successes, count, prior_mean=prior_mean, prior_strength=prior_strength)
    evidence_weight = min(_MAX_DIRECT_WEIGHT, count / (count + prior_strength))
    calibrated = (1.0 - evidence_weight) * raw + evidence_weight * posterior
    return {
        "raw_confidence": round(raw, 6),
        "calibrated_confidence": round(min(1.0, max(0.0, calibrated)), 6),
        "sample_count": count,
        "source": source,
        "risk_class": risk_class,
        "posterior_mean": round(posterior, 6),
    }


async def load_calibration_context(db, *, user_id: int | None, asset_type: str | None = None) -> dict[str, Any]:
    """Load only live, resolved, learning-eligible observations for a run."""
    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult

    query = (
        select(AnalysisResult)
        .where(AnalysisResult.alpha_return.is_not(None))
        .where(AnalysisResult.learning_eligible.is_(True))
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    if asset_type:
        query = query.where(AnalysisResult.asset_type == asset_type)
    rows = list((await db.execute(query)).scalars().all())
    return build_calibration_context(rows)
