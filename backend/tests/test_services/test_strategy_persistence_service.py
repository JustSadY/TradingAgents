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
        strategy_context={
            "strategy_id": 42,
            "expected_version": 5,
            "strategy_before": {"strategy_id": 42, "version": 5},
        },
        candidate_raw={
            "revision_action": "WEAKEN",
            "expected_version": 5,
            "strategy_before": {"strategy_id": 42, "version": 5},
            "strategy_after": {"status": "ACTIVE", "strategic_bias": "BULLISH", "conviction": 0.6},
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
async def test_persistence_rejects_rebuild_that_skips_active_thesis_invalidation() -> None:
    """The write boundary must retain lifecycle protection beyond graph schema validation."""

    row = _Row()
    session = _Session(row)

    result = await strategy_persistence_service.persist_completed_analysis_with_strategy(
        session,
        row_id=99,
        final_payload={
            "signal": "Hold",
            "portfolio_decision_json": {"rating": "Hold", "confidence_score": 0.5},
        },
        strategy_context={
            "strategy_id": 42,
            "expected_version": 5,
            "strategy_before": {"strategy_id": 42, "version": 5, "status": "ACTIVE"},
        },
        candidate_raw={
            "revision_action": "REBUILD",
            "expected_version": 5,
            "strategy_before": {"strategy_id": 42, "version": 5, "status": "ACTIVE"},
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
