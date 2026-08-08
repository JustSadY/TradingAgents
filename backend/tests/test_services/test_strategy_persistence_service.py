from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.repositories.asset_strategy import AssetStrategyCASResult
from backend.services import strategy_persistence_service


class _Row:
    status = "running"
    signal = None
    final_decision = ""
    portfolio_decision_json = None
    chart_annotations = None
    strategy_id = None
    strategy_before_json = None
    strategy_after_json = None
    strategy_candidate_json = None
    strategy_update_status = None
    strategy_before_version = None
    strategy_after_version = None


class _Session:
    def __init__(self, row: _Row) -> None:
        self.row = row
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, *_args, **_kwargs):
        return self.row


def _before() -> dict:
    return {
        "strategy_id": 42,
        "version": 5,
        "status": "ACTIVE",
        "strategic_bias": "BULLISH",
        "accepted_rating": "Buy",
        "conviction": 0.7,
        "thesis": "Existing thesis.",
    }


@pytest.mark.asyncio
async def test_cas_conflict_overrides_both_canonical_and_legacy_annotation(monkeypatch) -> None:
    row = _Row()
    session = _Session(row)
    monkeypatch.setattr(
        strategy_persistence_service,
        "compare_and_swap_asset_strategy",
        AsyncMock(
            return_value=AssetStrategyCASResult(
                outcome="conflict",
                strategy=None,
                version_record=None,
                expected_version=5,
                actual_version=6,
            )
        ),
    )

    result = await strategy_persistence_service.persist_completed_analysis_with_strategy(
        session,
        row_id=99,
        final_payload={
            "signal": "Sell",
            "portfolio_decision_json": {
                "rating": "Sell",
                "confidence_score": 0.91,
                "position_size_pct": 0.0,
            },
            "chart_annotations": {
                "portfolio_decision": {"rating": "Sell", "confidence_score": 0.91}
            },
        },
        strategy_context={"strategy_id": 42, "expected_version": 5, "strategy_before": _before()},
        candidate_raw={
            "revision_action": "WEAKEN",
            "expected_version": 5,
            "strategy_before": _before(),
            "strategy_after": {
                **_before(),
                "version": 6,
                "conviction": 0.6,
            },
        },
        user_id=7,
        ticker="NVDA",
        asset_type="stock",
        trade_date="2026-08-08",
        learning_eligible=True,
    )

    assert result.status == "conflict"
    assert result.decision_override is not None
    assert row.signal == "Hold"
    assert row.portfolio_decision_json["rating"] == "Hold"
    assert row.chart_annotations["portfolio_decision"]["rating"] == "Hold"
    assert row.strategy_update_status == "conflict"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)


@pytest.mark.asyncio
async def test_persistence_rejects_weaken_that_flips_strategic_bias() -> None:
    row = _Row()
    session = _Session(row)

    result = await strategy_persistence_service.persist_completed_analysis_with_strategy(
        session,
        row_id=99,
        final_payload={"portfolio_decision_json": {"rating": "Hold", "confidence_score": 0.6}},
        strategy_context={"strategy_id": 42, "expected_version": 5, "strategy_before": _before()},
        candidate_raw={
            "revision_action": "WEAKEN",
            "expected_version": 5,
            "strategy_before": _before(),
            "strategy_after": {
                **_before(),
                "version": 6,
                "conviction": 0.5,
                "strategic_bias": "BEARISH",
            },
        },
        user_id=7,
        ticker="NVDA",
        asset_type="stock",
        trade_date="2026-08-08",
        learning_eligible=True,
    )

    assert result.status == "candidate_invalid"
    assert "cannot change strategic_bias" in (result.reason or "")
    assert row.strategy_update_status == "candidate_invalid"


@pytest.mark.asyncio
async def test_persistence_rejects_unknown_invalidation_id() -> None:
    row = _Row()
    session = _Session(row)
    before = _before()

    result = await strategy_persistence_service.persist_completed_analysis_with_strategy(
        session,
        row_id=99,
        final_payload={
            "portfolio_decision_json": {"rating": "Sell", "confidence_score": 0.8, "position_size_pct": 0},
            "analysis_plan_json": {
                "invalidations_to_check": [
                    {"condition_id": "known_condition", "severity": "critical"}
                ]
            },
            "synthesis_json": {
                "triggered_invalidations": [
                    {
                        "condition_id": "hallucinated_condition",
                        "severity": "critical",
                        "evidence_ids": ["e1"],
                    }
                ]
            },
        },
        strategy_context={"strategy_id": 42, "expected_version": 5, "strategy_before": before},
        candidate_raw={
            "revision_action": "INVALIDATE",
            "expected_version": 5,
            "strategy_before": before,
            "strategy_after": {**before, "version": 6, "status": "INVALIDATED"},
            "triggered_invalidations": [
                {
                    "condition_id": "hallucinated_condition",
                    "severity": "critical",
                    "evidence_ids": ["e1"],
                }
            ],
        },
        user_id=7,
        ticker="NVDA",
        asset_type="stock",
        trade_date="2026-08-08",
        learning_eligible=True,
    )

    assert result.status == "candidate_invalid"
    assert "validated material/critical" in (result.reason or "")


@pytest.mark.asyncio
async def test_persistence_rejects_rebuild_that_skips_active_thesis_invalidation() -> None:
    row = _Row()
    session = _Session(row)

    result = await strategy_persistence_service.persist_completed_analysis_with_strategy(
        session,
        row_id=99,
        final_payload={
            "signal": "Hold",
            "portfolio_decision_json": {"rating": "Hold", "confidence_score": 0.5},
        },
        strategy_context={"strategy_id": 42, "expected_version": 5, "strategy_before": _before()},
        candidate_raw={
            "revision_action": "REBUILD",
            "expected_version": 5,
            "strategy_before": _before(),
            "strategy_after": {
                "ticker": "NVDA",
                "asset_type": "stock",
                "status": "ACTIVE",
                "version": 1,
                "strategic_bias": "BEARISH",
                "conviction": 0.7,
                "thesis": "Unvalidated replacement.",
            },
        },
        user_id=7,
        ticker="NVDA",
        asset_type="stock",
        trade_date="2026-08-08",
        learning_eligible=True,
    )

    assert result.status == "candidate_invalid"
    assert result.reason == "REBUILD requires an INVALIDATED or CLOSED predecessor"
    assert row.strategy_update_status == "candidate_invalid"
    session.commit.assert_awaited_once()