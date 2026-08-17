"""Point-in-time strategy context for an analysis run.

The active asset strategy is intentionally **not** vector memory. This module
loads one exact belief before the graph starts, turns it into a graph-safe
snapshot, and produces a deliberately blind planning context for fresh
analysts. Nodes never receive a database session: all persistence occurs only
after the graph finishes through :mod:`strategy_persistence_service`.

Historical and time-travel runs use the immutable version ledger as-of both
the requested business time and the exact time at which knowledge was allowed
to exist. Keeping those clocks separate prevents later same-day revisions from
leaking into an earlier checkpoint replay.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.asset_strategy import (
    get_active_asset_strategy,
    get_latest_asset_strategy,
    get_strategy_version_as_of,
    strategy_state_snapshot,
)
from backend.repositories.strategy_context import get_last_accepted_analysis


def _as_utc_day_end(trade_date: str | datetime) -> datetime:
    """Resolve an ISO business date to the end of that UTC business day."""
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


def _as_utc_instant(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    decision = _json_mapping(getattr(row, "portfolio_decision_json", None))
    return decision or None


def _blind_planning_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Return only hypotheses/questions, never the old rating or conviction."""
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
    business_as_of: datetime | None,
    recorded_as_of: datetime | None,
) -> dict[str, Any] | None:
    """Load the last accepted canonical decision in the same tenant scope."""
    last_analysis_id = (strategy_snapshot or {}).get("last_analysis_id")
    row = await get_last_accepted_analysis(
        db,
        user_id=user_id,
        ticker=ticker,
        asset_type=asset_type,
        last_analysis_id=last_analysis_id if isinstance(last_analysis_id, int) else None,
        business_as_of=business_as_of,
        recorded_as_of=recorded_as_of,
    )
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
    knowledge_cutoff: datetime | None = None,
) -> dict[str, Any]:
    """Load an exact strategy snapshot and an analyst-safe neutral context.

    ``trade_date`` is business time. ``knowledge_cutoff`` is recorded/system
    time. Ordinary historical analysis defaults to the end of the requested
    business day. Time Travel supplies the selected checkpoint timestamp
    explicitly so later same-day knowledge cannot leak into the replay.
    """
    ticker = ticker.upper()
    asset_type = asset_type.lower()
    business_as_of = _as_utc_day_end(trade_date)
    recorded_as_of = min(_as_utc_instant(knowledge_cutoff, business_as_of), business_as_of)

    snapshot: dict[str, Any] | None = None
    source = "none"

    if historical_mode:
        version = await get_strategy_version_as_of(
            db,
            user_id=user_id,
            ticker=ticker,
            asset_type=asset_type,
            effective_at=business_as_of,
            recorded_at=recorded_as_of,
        )
        if version is not None and isinstance(version.after_state, dict):
            snapshot = dict(version.after_state)
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
        business_as_of=business_as_of if historical_mode else None,
        recorded_as_of=recorded_as_of if historical_mode else None,
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
        "as_of": business_as_of.isoformat(),
        "knowledge_cutoff": recorded_as_of.isoformat(),
    }


__all__ = ["load_strategy_context"]
