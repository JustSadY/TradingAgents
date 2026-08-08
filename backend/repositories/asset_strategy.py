"""Repository operations for exact-state asset strategies.

These functions intentionally call ``flush`` rather than ``commit``.  An
analysis orchestration layer can therefore persist the accepted decision, its
strategy revision, and its analysis result in one transaction.  Callers own
the final commit/rollback boundary.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.asset_strategy import ASSET_STRATEGY_ACTIVE, AssetStrategy, AssetStrategyVersion

CASOutcome = Literal["updated", "conflict", "not_found"]
_UNSET = object()

# Scope columns, timestamps managed by the repository, and version identifiers
# are deliberately excluded.  A strategy's identity must never be accidentally
# changed by a decision-reconciliation write.
_MUTABLE_STATE_FIELDS = frozenset(
    {
        "status",
        "strategic_bias",
        "conviction",
        "accepted_rating",
        "thesis",
        "key_drivers",
        "watch_conditions",
        "invalidation_conditions",
        "open_questions",
        "regime_assumption",
        "time_horizon",
    }
)
_LIST_DEFAULT_FIELDS = frozenset(
    {
        "key_drivers",
        "watch_conditions",
        "invalidation_conditions",
        "open_questions",
    }
)
_DICT_DEFAULT_FIELDS = frozenset({"regime_assumption"})


@dataclass(frozen=True, slots=True)
class AssetStrategyCASResult:
    """Result of a compare-and-swap mutation.

    On ``conflict``, ``strategy`` is the latest persisted strategy and no
    current row or immutable history row was written by this call.  On
    ``not_found`` it is ``None``.  This lets callers return a structured
    conflict instead of overwriting a concurrent strategy revision.
    """

    outcome: CASOutcome
    strategy: AssetStrategy | None
    version_record: AssetStrategyVersion | None
    expected_version: int
    actual_version: int | None

    @property
    def applied(self) -> bool:
        return self.outcome == "updated"

    @property
    def conflict(self) -> bool:
        return self.outcome == "conflict"


def _utc(value: datetime | None, *, default: datetime | None = None) -> datetime:
    value = value or default or datetime.now(UTC)
    if value.tzinfo is None:
        # Analysis timestamps are defined in UTC across the backend.  Treat a
        # legacy/naive input as UTC rather than allowing database-dependent
        # local-time interpretation.
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_ticker(ticker: str) -> str:
    value = ticker.strip().upper()
    if not value:
        raise ValueError("ticker must not be empty")
    if len(value) > 50:
        raise ValueError("ticker must be at most 50 characters")
    return value


def _normalize_asset_type(asset_type: str) -> str:
    value = asset_type.strip().lower()
    if not value:
        raise ValueError("asset_type must not be empty")
    if len(value) > 20:
        raise ValueError("asset_type must be at most 20 characters")
    return value


def _copy_json(value: Any) -> Any:
    """Detach snapshots from caller-owned mutable values."""

    return copy.deepcopy(value)


def _normalized_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    values = dict(state or {})
    unknown = set(values).difference(_MUTABLE_STATE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported asset strategy state fields: {', '.join(sorted(unknown))}")

    for field in _LIST_DEFAULT_FIELDS:
        if field in values:
            values[field] = [] if values[field] is None else _copy_json(values[field])
    for field in _DICT_DEFAULT_FIELDS:
        if field in values:
            values[field] = {} if values[field] is None else _copy_json(values[field])

    if "status" in values:
        values["status"] = str(values["status"]).strip().upper()
        if not values["status"]:
            raise ValueError("status must not be empty")
    if "strategic_bias" in values:
        values["strategic_bias"] = str(values["strategic_bias"]).strip().upper()
        if not values["strategic_bias"]:
            raise ValueError("strategic_bias must not be empty")
    if "accepted_rating" in values and values["accepted_rating"] is not None:
        values["accepted_rating"] = str(values["accepted_rating"]).strip().upper() or None
    if "conviction" in values:
        conviction = float(values["conviction"])
        if not 0.0 <= conviction <= 1.0:
            raise ValueError("conviction must be between 0.0 and 1.0")
        values["conviction"] = conviction
    if "thesis" in values:
        values["thesis"] = str(values["thesis"] or "")
    if "time_horizon" in values and values["time_horizon"] is not None:
        values["time_horizon"] = str(values["time_horizon"]).strip() or None
    return values


def strategy_state_snapshot(strategy: AssetStrategy) -> dict[str, Any]:
    """Return a JSON-safe, detached state snapshot for the audit ledger."""

    def iso(value: datetime | None) -> str | None:
        return _utc(value).isoformat() if value else None

    return {
        "strategy_id": strategy.id,
        "user_id": strategy.user_id,
        "ticker": strategy.ticker,
        "asset_type": strategy.asset_type,
        "status": strategy.status,
        "version": strategy.version,
        "strategic_bias": strategy.strategic_bias,
        "conviction": strategy.conviction,
        "accepted_rating": strategy.accepted_rating,
        "thesis": strategy.thesis,
        "key_drivers": _copy_json(strategy.key_drivers),
        "watch_conditions": _copy_json(strategy.watch_conditions),
        "invalidation_conditions": _copy_json(strategy.invalidation_conditions),
        "open_questions": _copy_json(strategy.open_questions),
        "regime_assumption": _copy_json(strategy.regime_assumption),
        "time_horizon": strategy.time_horizon,
        "last_analysis_id": strategy.last_analysis_id,
        "effective_at": iso(strategy.effective_at),
        "recorded_at": iso(strategy.recorded_at),
        "last_reviewed_at": iso(strategy.last_reviewed_at),
    }


def _scope_statement(
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    active_only: bool = False,
) -> Select[tuple[AssetStrategy]]:
    statement = select(AssetStrategy).where(
        AssetStrategy.ticker == _normalize_ticker(ticker),
        AssetStrategy.asset_type == _normalize_asset_type(asset_type),
    )
    if user_id is None:
        statement = statement.where(AssetStrategy.user_id.is_(None))
    else:
        statement = statement.where(AssetStrategy.user_id == user_id)
    if active_only:
        statement = statement.where(AssetStrategy.status == ASSET_STRATEGY_ACTIVE)
    return statement


async def get_active_asset_strategy(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str = "stock",
    for_update: bool = False,
) -> AssetStrategy | None:
    """Fetch the sole active current strategy for an exact owner/ticker scope."""

    statement = _scope_statement(
        user_id=user_id,
        ticker=ticker,
        asset_type=asset_type,
        active_only=True,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_latest_asset_strategy(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str = "stock",
) -> AssetStrategy | None:
    """Return the newest lineage when no ACTIVE strategy currently exists.

    An invalidated thesis is intentionally no longer ``ACTIVE``. It is still
    valuable context for the next neutral investigation, though: otherwise a
    replacement would look like an unrelated ``CREATE`` instead of a traceable
    ``REBUILD`` of the invalidated lineage. Callers should prefer
    :func:`get_active_asset_strategy` and use this only as an exact-state
    fallback.
    """

    statement = _scope_statement(
        user_id=user_id,
        ticker=ticker,
        asset_type=asset_type,
    ).order_by(
        AssetStrategy.recorded_at.desc(),
        AssetStrategy.id.desc(),
    )
    result = await db.execute(statement.limit(1))
    return result.scalar_one_or_none()


async def get_asset_strategy_by_id(db: AsyncSession, strategy_id: int) -> AssetStrategy | None:
    result = await db.execute(
        select(AssetStrategy)
        .where(AssetStrategy.id == strategy_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_asset_strategy_versions(
    db: AsyncSession,
    *,
    strategy_id: int,
    limit: int | None = None,
) -> list[AssetStrategyVersion]:
    statement = (
        select(AssetStrategyVersion)
        .where(AssetStrategyVersion.strategy_id == strategy_id)
        .order_by(AssetStrategyVersion.version.asc())
    )
    if limit is not None:
        statement = statement.limit(max(1, limit))
    result = await db.execute(statement)
    return list(result.scalars().all())


async def list_asset_strategy_versions_for_asset(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str = "stock",
    limit: int | None = None,
) -> list[AssetStrategyVersion]:
    """Return the complete immutable history across strategy lineages.

    A ``REBUILD`` intentionally closes one current row and starts another.
    Looking up only the currently ACTIVE row would hide the reasoning that
    invalidated the prior thesis, so audit/history views use this asset-scoped
    ledger query instead.
    """

    statement = (
        select(AssetStrategyVersion)
        .join(AssetStrategy, AssetStrategy.id == AssetStrategyVersion.strategy_id)
        .where(
            AssetStrategy.ticker == _normalize_ticker(ticker),
            AssetStrategy.asset_type == _normalize_asset_type(asset_type),
        )
        .order_by(
            AssetStrategyVersion.effective_at.desc(),
            AssetStrategyVersion.recorded_at.desc(),
            AssetStrategyVersion.id.desc(),
        )
    )
    if user_id is None:
        statement = statement.where(AssetStrategy.user_id.is_(None))
    else:
        statement = statement.where(AssetStrategy.user_id == user_id)
    if limit is not None:
        statement = statement.limit(max(1, limit))
    result = await db.execute(statement)
    return list(result.scalars().all())


async def get_strategy_version_as_of(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str = "stock",
    effective_at: datetime,
    recorded_at: datetime | None = None,
) -> AssetStrategyVersion | None:
    """Return the belief valid at one business time and known at another.

    ``recorded_at`` is optional.  When provided, it prevents a replay from
    seeing a strategy revision that had not yet been recorded at that point
    in time, closing the common historical future-leakage path.
    """

    statement = (
        select(AssetStrategyVersion)
        .join(AssetStrategy, AssetStrategy.id == AssetStrategyVersion.strategy_id)
        .where(
            AssetStrategy.ticker == _normalize_ticker(ticker),
            AssetStrategy.asset_type == _normalize_asset_type(asset_type),
            AssetStrategyVersion.effective_at <= _utc(effective_at),
        )
        .order_by(
            AssetStrategyVersion.effective_at.desc(),
            AssetStrategyVersion.recorded_at.desc(),
            AssetStrategyVersion.id.desc(),
        )
        .limit(1)
    )
    if user_id is None:
        statement = statement.where(AssetStrategy.user_id.is_(None))
    else:
        statement = statement.where(AssetStrategy.user_id == user_id)
    if recorded_at is not None:
        statement = statement.where(AssetStrategyVersion.recorded_at <= _utc(recorded_at))
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def create_asset_strategy(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str = "stock",
    state: Mapping[str, Any] | None = None,
    analysis_id: int | None = None,
    effective_at: datetime | None = None,
    recorded_at: datetime | None = None,
    last_reviewed_at: datetime | None = None,
    revision_action: str = "CREATE",
    triggered_invalidations: list | dict | None = None,
    supporting_evidence: list | dict | None = None,
    regime_before: dict | list | None = None,
    regime_after: dict | list | None = None,
    pm_proposed_rating: str | None = None,
    change_strength: float | None = None,
) -> AssetStrategy:
    """Create a strategy and its immutable version-1 ledger entry.

    The active-scope unique index is intentionally left to the database to
    arbitrate concurrent first analyses.  An ``IntegrityError`` means a peer
    created the active strategy first; callers can re-load it and retry their
    decision flow rather than overwrite it.
    """

    now = datetime.now(UTC)
    effective = _utc(effective_at, default=now)
    recorded = _utc(recorded_at, default=now)
    values = _normalized_state(state)
    values.setdefault("status", ASSET_STRATEGY_ACTIVE)
    values.setdefault("last_reviewed_at", _utc(last_reviewed_at, default=effective))
    values["last_analysis_id"] = analysis_id

    strategy = AssetStrategy(
        user_id=user_id,
        ticker=_normalize_ticker(ticker),
        asset_type=_normalize_asset_type(asset_type),
        effective_at=effective,
        recorded_at=recorded,
        **values,
    )
    db.add(strategy)
    await db.flush()

    after_state = strategy_state_snapshot(strategy)
    version = AssetStrategyVersion(
        strategy_id=strategy.id,
        version=strategy.version,
        analysis_id=analysis_id,
        revision_action=revision_action.strip().upper() or "CREATE",
        before_state=None,
        after_state=after_state,
        triggered_invalidations=_copy_json(triggered_invalidations or []),
        supporting_evidence=_copy_json(supporting_evidence or []),
        regime_before=_copy_json(regime_before),
        regime_after=_copy_json(regime_after if regime_after is not None else strategy.regime_assumption),
        pm_proposed_rating=(str(pm_proposed_rating).strip().upper() if pm_proposed_rating else None),
        accepted_rating=strategy.accepted_rating,
        change_strength=change_strength,
        effective_at=effective,
        recorded_at=recorded,
    )
    db.add(version)
    await db.flush()
    return strategy


async def compare_and_swap_asset_strategy(
    db: AsyncSession,
    *,
    strategy_id: int,
    expected_version: int,
    updates: Mapping[str, Any],
    revision_action: str,
    analysis_id: int | None | object = _UNSET,
    effective_at: datetime | None = None,
    recorded_at: datetime | None = None,
    triggered_invalidations: list | dict | None = None,
    supporting_evidence: list | dict | None = None,
    regime_before: dict | list | None = None,
    regime_after: dict | list | None = None,
    pm_proposed_rating: str | None = None,
    change_strength: float | None = None,
) -> AssetStrategyCASResult:
    """Atomically revise a strategy only if ``expected_version`` is current.

    A successful mutation increments ``version`` and appends exactly one
    immutable ledger row.  A stale caller receives ``outcome='conflict'`` and
    the latest strategy without changing either table.
    """

    if expected_version < 1:
        raise ValueError("expected_version must be positive")
    action = revision_action.strip().upper()
    if not action:
        raise ValueError("revision_action must not be empty")

    current = await get_asset_strategy_by_id(db, strategy_id)
    if current is None:
        return AssetStrategyCASResult(
            outcome="not_found",
            strategy=None,
            version_record=None,
            expected_version=expected_version,
            actual_version=None,
        )

    before_state = strategy_state_snapshot(current)
    before_regime = _copy_json(current.regime_assumption)
    now = datetime.now(UTC)
    effective = _utc(effective_at, default=now)
    recorded = _utc(recorded_at, default=now)
    values = _normalized_state(updates)
    values.update(
        {
            "version": expected_version + 1,
            "effective_at": effective,
            "recorded_at": recorded,
            "updated_at": now,
            "last_reviewed_at": effective,
        }
    )
    if analysis_id is not _UNSET:
        values["last_analysis_id"] = analysis_id

    result = await db.execute(
        update(AssetStrategy)
        .where(
            AssetStrategy.id == strategy_id,
            AssetStrategy.version == expected_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        latest = await get_asset_strategy_by_id(db, strategy_id)
        return AssetStrategyCASResult(
            outcome="conflict",
            strategy=latest,
            version_record=None,
            expected_version=expected_version,
            actual_version=latest.version if latest else None,
        )

    await db.flush()
    strategy = await get_asset_strategy_by_id(db, strategy_id)
    # The update predicate succeeded, therefore a row must still exist.  This
    # guard keeps static type checkers and callers safe in a pathological
    # concurrent deletion race.
    if strategy is None:
        return AssetStrategyCASResult(
            outcome="not_found",
            strategy=None,
            version_record=None,
            expected_version=expected_version,
            actual_version=None,
        )

    after_state = strategy_state_snapshot(strategy)
    version = AssetStrategyVersion(
        strategy_id=strategy.id,
        version=strategy.version,
        analysis_id=strategy.last_analysis_id if analysis_id is _UNSET else analysis_id,
        revision_action=action,
        before_state=before_state,
        after_state=after_state,
        triggered_invalidations=_copy_json(triggered_invalidations or []),
        supporting_evidence=_copy_json(supporting_evidence or []),
        regime_before=_copy_json(regime_before if regime_before is not None else before_regime),
        regime_after=_copy_json(regime_after if regime_after is not None else strategy.regime_assumption),
        pm_proposed_rating=(str(pm_proposed_rating).strip().upper() if pm_proposed_rating else None),
        accepted_rating=strategy.accepted_rating,
        change_strength=change_strength,
        effective_at=effective,
        recorded_at=recorded,
    )
    db.add(version)
    await db.flush()
    return AssetStrategyCASResult(
        outcome="updated",
        strategy=strategy,
        version_record=version,
        expected_version=expected_version,
        actual_version=strategy.version,
    )


async def touch_asset_strategy_review(
    db: AsyncSession,
    *,
    strategy_id: int,
    expected_version: int,
    reviewed_at: datetime | None = None,
    analysis_id: int | None | object = _UNSET,
) -> AssetStrategyCASResult:
    """Record a non-material review without creating a needless revision.

    ``KEEP`` reviews are metadata-only: the strategy belief, its version, and
    its immutable version ledger stay unchanged.  They still use the expected
    version predicate so a stale analysis cannot overwrite ``last_analysis``
    metadata after a material revision happened.
    """

    if expected_version < 1:
        raise ValueError("expected_version must be positive")

    current = await get_asset_strategy_by_id(db, strategy_id)
    if current is None:
        return AssetStrategyCASResult("not_found", None, None, expected_version, None)

    reviewed = _utc(reviewed_at)
    values: dict[str, Any] = {
        "last_reviewed_at": reviewed,
        "updated_at": datetime.now(UTC),
    }
    if analysis_id is not _UNSET:
        values["last_analysis_id"] = analysis_id

    result = await db.execute(
        update(AssetStrategy)
        .where(
            AssetStrategy.id == strategy_id,
            AssetStrategy.version == expected_version,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        latest = await get_asset_strategy_by_id(db, strategy_id)
        return AssetStrategyCASResult(
            "conflict",
            latest,
            None,
            expected_version,
            latest.version if latest else None,
        )

    await db.flush()
    strategy = await get_asset_strategy_by_id(db, strategy_id)
    if strategy is None:
        return AssetStrategyCASResult("not_found", None, None, expected_version, None)
    return AssetStrategyCASResult("updated", strategy, None, expected_version, strategy.version)
