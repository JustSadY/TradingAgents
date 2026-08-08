from __future__ import annotations

from types import SimpleNamespace

from backend.models.analysis import AnalysisResult
from backend.services.confidence_calibration_service import (
    build_calibration_context,
    calibrate_confidence,
    load_calibration_context,
)


def _resolved_row(*, rating: str, confidence: float, alpha: float):
    return SimpleNamespace(
        portfolio_decision_json={"rating": rating, "confidence_score": confidence},
        signal=rating,
        alpha_return=alpha,
    )


def test_calibration_shrinks_overconfident_sparse_or_underperforming_pm_scores():
    # Three resolved long calls with only one success are enough to pull an
    # 86% raw claim downward, but not enough to create an extreme posterior.
    context = build_calibration_context(
        [
            _resolved_row(rating="Buy", confidence=0.86, alpha=0.02),
            _resolved_row(rating="Buy", confidence=0.86, alpha=-0.03),
            _resolved_row(rating="Overweight", confidence=0.86, alpha=-0.01),
        ]
    )
    result = calibrate_confidence(0.86, "Buy", context)

    assert result["sample_count"] == 3
    assert result["calibrated_confidence"] < 0.86
    assert 0.0 <= result["calibrated_confidence"] <= 1.0


async def test_calibration_context_excludes_non_learning_replays(db_session, test_user):
    db_session.add_all(
        [
            AnalysisResult(
                user_id=test_user.id,
                ticker="NVDA",
                trade_date="2026-07-01",
                asset_type="stock",
                status="completed",
                learning_eligible=True,
                alpha_return=0.03,
                portfolio_decision_json={"rating": "Buy", "confidence_score": 0.8},
            ),
            AnalysisResult(
                user_id=test_user.id,
                ticker="NVDA",
                trade_date="2025-07-01",
                asset_type="stock",
                status="completed",
                analysis_mode="historical",
                learning_eligible=False,
                alpha_return=-0.9,
                portfolio_decision_json={"rating": "Buy", "confidence_score": 0.8},
            ),
        ]
    )
    await db_session.flush()

    context = await load_calibration_context(db_session, user_id=test_user.id, asset_type="stock")

    assert context["total_samples"] == 1
    assert context["total_successes"] == 1
