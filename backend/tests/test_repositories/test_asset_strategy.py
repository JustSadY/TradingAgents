from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models.analysis import AnalysisResult
from backend.models.asset_strategy import ASSET_STRATEGY_ACTIVE, AssetStrategy
from backend.repositories.asset_strategy import (
    compare_and_swap_asset_strategy,
    create_asset_strategy,
    get_active_asset_strategy,
    get_strategy_version_as_of,
    list_asset_strategy_versions,
    strategy_state_snapshot,
    touch_asset_strategy_review,
)


async def test_create_active_strategy_adds_initial_immutable_snapshot(db_session, test_user):
    effective_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
    recorded_at = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)
    strategy = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker=" nvda ",
        state={
            "strategic_bias": "bullish",
            "conviction": 0.73,
            "accepted_rating": "Overweight",
            "thesis": "AI infrastructure spending remains structurally strong.",
            "key_drivers": ["hyperscaler CAPEX"],
            "invalidation_conditions": ["two quarters of slowing data-center growth"],
            "regime_assumption": {"risk": "risk_on"},
        },
        effective_at=effective_at,
        recorded_at=recorded_at,
        supporting_evidence=[{"source_family": "fundamentals", "strength": 0.8}],
    )

    assert strategy.ticker == "NVDA"
    assert strategy.asset_type == "stock"
    assert strategy.status == ASSET_STRATEGY_ACTIVE
    assert strategy.version == 1
    assert strategy.effective_at == effective_at
    assert strategy.recorded_at == recorded_at

    current = await get_active_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="nvda",
        asset_type="stock",
    )
    assert current is not None
    assert current.id == strategy.id

    versions = await list_asset_strategy_versions(db_session, strategy_id=strategy.id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].revision_action == "CREATE"
    assert versions[0].before_state is None
    assert versions[0].after_state["ticker"] == "NVDA"
    assert versions[0].after_state["conviction"] == pytest.approx(0.73)
    assert versions[0].supporting_evidence == [{"source_family": "fundamentals", "strength": 0.8}]


async def test_active_scope_unique_index_handles_nullable_user_id_in_sqlite(db_session, test_user):
    await create_asset_strategy(db_session, user_id=None, ticker="NVDA")
    await create_asset_strategy(db_session, user_id=test_user.id, ticker="NVDA")

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await create_asset_strategy(db_session, user_id=None, ticker="nvda")

    # An inactive historical row does not consume the one active-strategy slot.
    inactive = AssetStrategy(
        user_id=None,
        ticker="NVDA",
        asset_type="stock",
        status="INVALIDATED",
        effective_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
    )
    db_session.add(inactive)
    await db_session.flush()

    result = await db_session.execute(
        select(AssetStrategy).where(
            AssetStrategy.user_id.is_(None),
            AssetStrategy.ticker == "NVDA",
        )
    )
    assert len(result.scalars().all()) == 2


async def test_compare_and_swap_appends_history_and_rejects_stale_writer(db_session, test_user):
    strategy = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={
            "strategic_bias": "BULLISH",
            "conviction": 0.78,
            "accepted_rating": "BUY",
            "regime_assumption": {"risk": "RISK_ON"},
        },
    )
    original_snapshot = strategy_state_snapshot(strategy)

    applied = await compare_and_swap_asset_strategy(
        db_session,
        strategy_id=strategy.id,
        expected_version=1,
        updates={
            "strategic_bias": "BULLISH",
            "conviction": 0.69,
            "accepted_rating": "OVERWEIGHT",
            "watch_conditions": ["valuation premium"],
            "regime_assumption": {"risk": "RISK_ON", "volatility": "ELEVATED"},
        },
        revision_action="WEAKEN",
        supporting_evidence=[{"source_family": "valuation", "strength": 0.65}],
    )

    assert applied.applied
    assert applied.outcome == "updated"
    assert applied.strategy is not None
    assert applied.strategy.version == 2
    assert applied.strategy.conviction == pytest.approx(0.69)
    assert applied.version_record is not None
    assert applied.version_record.before_state == original_snapshot
    assert applied.version_record.after_state["version"] == 2
    assert applied.version_record.regime_before == {"risk": "RISK_ON"}
    assert applied.version_record.regime_after == {"risk": "RISK_ON", "volatility": "ELEVATED"}

    stale = await compare_and_swap_asset_strategy(
        db_session,
        strategy_id=strategy.id,
        expected_version=1,
        updates={"strategic_bias": "BEARISH", "conviction": 0.99, "accepted_rating": "SELL"},
        revision_action="INVALIDATE",
    )
    assert stale.conflict
    assert stale.actual_version == 2
    assert stale.strategy is not None
    assert stale.strategy.strategic_bias == "BULLISH"
    assert stale.strategy.accepted_rating == "OVERWEIGHT"

    versions = await list_asset_strategy_versions(db_session, strategy_id=strategy.id)
    assert [item.version for item in versions] == [1, 2]
    assert [item.revision_action for item in versions] == ["CREATE", "WEAKEN"]


async def test_keep_review_uses_expected_version_without_artificial_revision(db_session, test_user):
    strategy = await create_asset_strategy(db_session, user_id=test_user.id, ticker="NVDA")
    reviewed_at = datetime(2026, 8, 7, 15, tzinfo=UTC)

    result = await touch_asset_strategy_review(
        db_session,
        strategy_id=strategy.id,
        expected_version=1,
        reviewed_at=reviewed_at,
    )
    assert result.applied
    assert result.strategy is not None
    assert result.strategy.version == 1
    # SQLite drops the tzinfo that PostgreSQL's timestamptz preserves, so
    # compare the instant rather than the tz-awareness of the round trip.
    stored = result.strategy.last_reviewed_at
    assert (stored if stored.tzinfo else stored.replace(tzinfo=UTC)) == reviewed_at
    assert await list_asset_strategy_versions(db_session, strategy_id=strategy.id)
    assert len(await list_asset_strategy_versions(db_session, strategy_id=strategy.id)) == 1

    # expected_version must be positive rather than silently using version 0.
    with pytest.raises(ValueError, match="expected_version"):
        await touch_asset_strategy_review(db_session, strategy_id=strategy.id, expected_version=0)


async def test_bitemporal_strategy_lookup_does_not_see_later_recorded_revision(db_session, test_user):
    effective_v1 = datetime(2026, 1, 2, 10, tzinfo=UTC)
    recorded_v1 = datetime(2026, 1, 2, 10, 5, tzinfo=UTC)
    effective_v2 = datetime(2026, 2, 3, 10, tzinfo=UTC)
    recorded_v2 = datetime(2026, 2, 4, 9, tzinfo=UTC)
    strategy = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={"strategic_bias": "BULLISH", "conviction": 0.7},
        effective_at=effective_v1,
        recorded_at=recorded_v1,
    )
    revised = await compare_and_swap_asset_strategy(
        db_session,
        strategy_id=strategy.id,
        expected_version=1,
        updates={"strategic_bias": "BEARISH", "conviction": 0.8},
        revision_action="INVALIDATE",
        effective_at=effective_v2,
        recorded_at=recorded_v2,
    )
    assert revised.applied

    known_before_revision = await get_strategy_version_as_of(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        effective_at=effective_v2 + timedelta(hours=1),
        recorded_at=recorded_v2 - timedelta(minutes=1),
    )
    assert known_before_revision is not None
    assert known_before_revision.version == 1
    assert known_before_revision.after_state["strategic_bias"] == "BULLISH"

    known_after_revision = await get_strategy_version_as_of(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        effective_at=effective_v2 + timedelta(hours=1),
        recorded_at=recorded_v2,
    )
    assert known_after_revision is not None
    assert known_after_revision.version == 2
    assert known_after_revision.after_state["strategic_bias"] == "BEARISH"


async def test_bitemporal_lookup_prefers_new_rebuild_lineage_when_timestamps_tie(db_session, test_user):
    """A replacement v1 is newer globally than a closed prior lineage's v2.

    Versions are local to a strategy lineage, so sorting by ``version`` ahead
    of the append-only ledger id would incorrectly resurrect the closed v2
    when both revisions share database timestamp precision.
    """

    event_at = datetime(2026, 8, 8, 12, tzinfo=UTC)
    prior = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={"strategic_bias": "BULLISH", "conviction": 0.7},
        effective_at=event_at,
        recorded_at=event_at,
    )
    closed = await compare_and_swap_asset_strategy(
        db_session,
        strategy_id=prior.id,
        expected_version=1,
        updates={"status": "CLOSED"},
        revision_action="REBUILD",
        effective_at=event_at,
        recorded_at=event_at,
    )
    assert closed.applied
    replacement = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={"strategic_bias": "BEARISH", "conviction": 0.8},
        effective_at=event_at,
        recorded_at=event_at,
        revision_action="REBUILD",
    )

    found = await get_strategy_version_as_of(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        effective_at=event_at,
        recorded_at=event_at,
    )
    assert found is not None
    assert found.strategy_id == replacement.id
    assert found.after_state["strategic_bias"] == "BEARISH"


async def test_analysis_foreign_keys_set_null_without_destroying_history(db_session, test_user):
    analysis = AnalysisResult(
        user_id=test_user.id,
        ticker="NVDA",
        trade_date="2026-08-08",
        asset_type="stock",
    )
    db_session.add(analysis)
    await db_session.flush()

    strategy = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        analysis_id=analysis.id,
    )
    versions = await list_asset_strategy_versions(db_session, strategy_id=strategy.id)
    assert versions[0].analysis_id == analysis.id

    await db_session.delete(analysis)
    await db_session.flush()
    await db_session.refresh(strategy)
    await db_session.refresh(versions[0])

    assert strategy.last_analysis_id is None
    assert versions[0].analysis_id is None
    assert versions[0].after_state["ticker"] == "NVDA"


async def test_version_ledger_rejects_normal_orm_mutation(db_session, test_user):
    strategy = await create_asset_strategy(db_session, user_id=test_user.id, ticker="NVDA")
    version = (await list_asset_strategy_versions(db_session, strategy_id=strategy.id))[0]
    version.revision_action = "TAMPERED"

    with pytest.raises(ValueError, match="immutable"):
        await db_session.flush()
    await db_session.rollback()
