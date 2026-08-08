"""Point-in-time strategy context for an analysis run.

The active asset strategy is intentionally **not** vector memory.  This module
loads one exact belief before the graph starts, turns it into a graph-safe
snapshot, and produces a deliberately blind planning context for fresh
analysts.  Nodes never receive a database session: all persistence occurs only
after the graph finishes through :mod:`strategy_persistence_service`.

Historical and time-travel runs use the immutable version ledger as-of both
the requested business time and the time at which that belief was recorded.
That prevents a later live strategy from leaking into an earlier replay.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.asset_strategy import (
    get_active_asset_strategy,
    get_latest_asset_strategy,
    get_strategy_version_as_of,
    strategy_state_snapshot,
)


def _as_utc_day_end(trade_date: str | datetime) -> datetime:
    """Resolve an ISO trade date to the end of that UTC business day.

    A date-only analysis sees facts recorded no later than that date.  We use
    the end rather than midnight so an intraday strategy review on the same
    date remains visible, while the ``recorded_at`` predicate still rejects
    all future knowledge.
    """

    if isinstance(trade_date, datetime):
        value = trade_date
    else:
        value = datetime.fromisoformat(str(trade_date).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    if value.hour == value.minute == value.second == value.microsecond == 0:
        return datetime.combine(value.date(), time.max, tzinfo=UTC)
    return value


def _json_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _decision_from_analysis(row: object | None) -> dict[str, Any] | None:
    if row is None:
        return None
    for raw in (
        getattr(row, "portfolio_decision_json", None),
        _json_mapping(getattr(row, "chart_annotations", None)).get("portfolio_decision"),
    ):
        decision = _json_mapping(raw)
        if decision:
            return decision
    return None


def _blind_planning_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Return only hypotheses/questions, never the old rating or conviction.

    The planner needs to know which assumptions require re-testing.  It must
    not know whether the prior strategy was Buy, Sell, or how strongly the
    system believed it; that information would turn a research agenda into a
    confirmation prompt.  The resulting plan is separately validated by the
    ``AnalysisPlan`` schema before analysts see it.
    """

    if not snapshot:
        return {
            "source_strategy_version": None,
            "prior_assumptions": [],
            "invalidation_conditions": [],
            "watch_conditions": [],
            "open_questions": [],
            "is_first_analysis": True,
        }

    invalidations = snapshot.get("invalidation_conditions")
    if not isinstance(invalidations, list):
        invalidations = []
    key_drivers = snapshot.get("key_drivers")
    if not isinstance(key_drivers, list):
        key_drivers = []
    watch_conditions = snapshot.get("watch_conditions")
    if not isinstance(watch_conditions, list):
        watch_conditions = []
    open_questions = snapshot.get("open_questions")
    if not isinstance(open_questions, list):
        open_questions = []
    return {
        "source_strategy_version": snapshot.get("version"),
        "prior_assumptions": [str(item) for item in key_drivers if str(item).strip()],
        "invalidation_conditions": invalidations,
        "watch_conditions": [str(item) for item in watch_conditions if str(item).strip()],
        "open_questions": [str(item) for item in open_questions if str(item).strip()],
        "is_first_analysis": False,
    }


async def _last_accepted_decision(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    strategy_snapshot: dict[str, Any] | None,
    as_of: datetime | None,
) -> dict[str, Any] | None:
    """Load the last accepted canonical decision in the same tenant scope."""

    from backend.models.analysis import AnalysisResult

    row = None
    # The mutable row's ``last_analysis_id`` is the fastest and most precise
    # answer for a live run.  A historical ledger deliberately does not append
    # a new strategy version for a KEEP review, however, so its immutable
    # ``after_state`` can legitimately point to an older analysis.  Replays
    # must therefore resolve the accepted decision from the point-in-time
    # analysis history instead of trusting that stale ledger pointer.
    last_analysis_id = (strategy_snapshot or {}).get("last_analysis_id")
    if as_of is None and isinstance(last_analysis_id, int):
        candidate = await db.get(AnalysisResult, last_analysis_id)
        if candidate is not None and candidate.status == "completed":
            row = candidate

    if row is None:
        stmt = (
            select(AnalysisResult)
            .where(
                AnalysisResult.ticker == ticker.upper(),
                AnalysisResult.asset_type == asset_type.lower(),
                AnalysisResult.status == "completed",
                AnalysisResult.learning_eligible.is_(True),
            )
            .order_by(AnalysisResult.trade_date.desc(), AnalysisResult.created_at.desc())
            .limit(1)
        )
        if user_id is None:
            stmt = stmt.where(AnalysisResult.user_id.is_(None))
        else:
            stmt = stmt.where(AnalysisResult.user_id == user_id)
        if as_of is not None:
            # Both business date and recorded time must be in the past.  A
            # later-created backfill for an old trade date is still future
            # knowledge from the perspective of this replay.
            stmt = stmt.where(
                AnalysisResult.trade_date <= as_of.date().isoformat(),
                AnalysisResult.created_at <= as_of,
            )
        row = (await db.execute(stmt)).scalar_one_or_none()
    return _decision_from_analysis(row)


async def load_strategy_context(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    trade_date: str | datetime,
    historical_mode: bool,
    learning_eligible: bool,
) -> dict[str, Any]:
    """Load an exact strategy snapshot and an analyst-safe neutral context.

    ``learning_eligible`` is returned as part of the context so every caller
    can audit why a strategy was or was not allowed to mutate at finalization.
    It is not inferred inside graph nodes.
    """

    ticker = ticker.upper()
    asset_type = asset_type.lower()
    as_of = _as_utc_day_end(trade_date)
    snapshot: dict[str, Any] | None = None
    source = "none"

    if historical_mode:
        version = await get_strategy_version_as_of(
            db,
            user_id=user_id,
            ticker=ticker,
            asset_type=asset_type,
            effective_at=as_of,
            recorded_at=as_of,
        )
        if version is not None and isinstance(version.after_state, dict):
            snapshot = dict(version.after_state)
            # The ledger snapshot has all row fields, but record a stable
            # version even for records created before this explicit field.
            snapshot.setdefault("strategy_id", version.strategy_id)
            snapshot.setdefault("version", version.version)
            source = "historical_version"
    else:
        strategy = await get_active_asset_strategy(
            db,
            user_id=user_id,
            ticker=ticker,
            asset_type=asset_type,
        )
        if strategy is not None:
            snapshot = strategy_state_snapshot(strategy)
            source = "active_strategy"
        else:
            # An explicitly invalidated/closed lineage is not active and must
            # never be presented as an active thesis. It remains the exact
            # predecessor for a later REBUILD, however; without this fallback
            # the next run would lose the lineage and create an unrelated v1.
            predecessor = await get_latest_asset_strategy(
                db,
                user_id=user_id,
                ticker=ticker,
                asset_type=asset_type,
            )
            if predecessor is not None:
                snapshot = strategy_state_snapshot(predecessor)
                source = "inactive_strategy_predecessor"

    previous_decision = await _last_accepted_decision(
        db,
        user_id=user_id,
        ticker=ticker,
        asset_type=asset_type,
        strategy_snapshot=snapshot,
        as_of=as_of if historical_mode else None,
    )
    return {
        "source": source,
        "strategy_before": snapshot,
        "expected_version": snapshot.get("version") if snapshot else None,
        "strategy_id": snapshot.get("strategy_id") if snapshot else None,
        "previous_accepted_decision": previous_decision,
        "blind_planning_context": _blind_planning_context(snapshot),
        "historical_mode": historical_mode,
        "learning_eligible": bool(learning_eligible),
        "as_of": as_of.isoformat(),
    }


__all__ = ["load_strategy_context"]
