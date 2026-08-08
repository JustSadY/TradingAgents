from datetime import UTC, datetime
from unittest.mock import AsyncMock

from backend.models.analysis import AnalysisResult
from backend.repositories.asset_strategy import create_asset_strategy, touch_asset_strategy_review
from backend.services import strategy_context_service
from backend.services.strategy_context_service import load_strategy_context


async def test_historical_context_uses_latest_keep_review_decision_without_future_leakage(db_session, test_user):
    """KEEP does not append a strategy version, so replay must query analyses.

    The v1 ledger intentionally retains the original ``last_analysis_id``.
    A later non-material review updates only the current row; historical
    context must still recover its accepted decision while excluding a future
    backfill with the same business date.
    """

    first_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
    review_at = datetime(2026, 8, 2, 12, tzinfo=UTC)
    future_recorded_at = datetime(2026, 8, 4, 12, tzinfo=UTC)
    initial = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-08-01",
        asset_type="stock",
        status="completed",
        learning_eligible=True,
        created_at=first_at,
        portfolio_decision_json={"rating": "Buy", "confidence_score": 0.7},
    )
    reviewed = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-08-02",
        asset_type="stock",
        status="completed",
        learning_eligible=True,
        created_at=review_at,
        portfolio_decision_json={"rating": "Hold", "confidence_score": 0.6},
    )
    future_backfill = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-08-02",
        asset_type="stock",
        status="completed",
        learning_eligible=True,
        created_at=future_recorded_at,
        portfolio_decision_json={"rating": "Sell", "confidence_score": 0.9},
    )
    db_session.add_all([initial, reviewed, future_backfill])
    await db_session.flush()

    strategy = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={
            "strategic_bias": "BULLISH",
            "conviction": 0.7,
            "thesis": "Initial thesis.",
        },
        analysis_id=initial.id,
        effective_at=first_at,
        recorded_at=first_at,
    )
    keep = await touch_asset_strategy_review(
        db_session,
        strategy_id=strategy.id,
        expected_version=1,
        reviewed_at=review_at,
        analysis_id=reviewed.id,
    )
    assert keep.applied

    context = await load_strategy_context(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        asset_type="stock",
        trade_date="2026-08-02",
        historical_mode=True,
        learning_eligible=False,
    )

    assert context["source"] == "historical_version"
    assert context["strategy_before"]["last_analysis_id"] == initial.id
    assert context["previous_accepted_decision"]["rating"] == "Hold"


async def test_live_context_uses_invalidated_predecessor_for_a_traceable_rebuild(monkeypatch):
    snapshot = {
        "strategy_id": 42,
        "ticker": "NVDA",
        "asset_type": "stock",
        "status": "INVALIDATED",
        "version": 3,
        "strategic_bias": "BULLISH",
        "conviction": 0.2,
        "thesis": "The prior thesis failed.",
        "key_drivers": ["Data-center demand"],
        "watch_conditions": [],
        "invalidation_conditions": [],
        "open_questions": [],
    }
    predecessor = object()
    get_active = AsyncMock(return_value=None)
    get_latest = AsyncMock(return_value=predecessor)
    get_previous = AsyncMock(return_value={"rating": "Hold", "confidence_score": 0.5})
    monkeypatch.setattr(strategy_context_service, "get_active_asset_strategy", get_active)
    monkeypatch.setattr(strategy_context_service, "get_latest_asset_strategy", get_latest)
    monkeypatch.setattr(strategy_context_service, "strategy_state_snapshot", lambda _: snapshot)
    monkeypatch.setattr(strategy_context_service, "_last_accepted_decision", get_previous)

    context = await load_strategy_context(
        object(),
        user_id=9,
        ticker="nvda",
        asset_type="stock",
        trade_date="2026-08-08",
        historical_mode=False,
        learning_eligible=True,
    )

    assert context["source"] == "inactive_strategy_predecessor"
    assert context["strategy_before"] == snapshot
    assert context["previous_accepted_decision"]["rating"] == "Hold"
    get_latest.assert_awaited_once()
