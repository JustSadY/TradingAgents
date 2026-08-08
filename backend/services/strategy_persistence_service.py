"""Transactional persistence for analysis results and exact asset strategies.

The graph only proposes a strategy revision.  This service is the single
write boundary that turns that candidate into a durable ``AssetStrategy``
version *and* writes the accepted canonical decision to ``AnalysisResult``.
It uses repository CAS operations, so two concurrent analyses cannot both
silently write ``v5 → v6`` for the same asset.
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.asset_strategy import (
    AssetStrategyCASResult,
    compare_and_swap_asset_strategy,
    create_asset_strategy,
    strategy_state_snapshot,
    touch_asset_strategy_review,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StrategyPersistenceResult:
    """Outcome used by the orchestrator to surface CAS and safety decisions."""

    status: str
    strategy_id: int | None
    before_snapshot: dict[str, Any] | None
    after_snapshot: dict[str, Any] | None
    before_version: int | None
    after_version: int | None
    decision_override: dict[str, Any] | None = None
    reason: str | None = None


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return copy.deepcopy(dumped) if isinstance(dumped, dict) else {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return copy.deepcopy(parsed) if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: object) -> list:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _as_dict(value: object) -> dict:
    return copy.deepcopy(value) if isinstance(value, Mapping) else {}


def _db_strategy_state(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Map a validated graph snapshot to repository-owned mutable columns."""

    status = str(snapshot.get("status") or "ACTIVE").upper()
    bias = str(snapshot.get("strategic_bias") or "Neutral").upper()
    rating = snapshot.get("accepted_rating")
    if rating is not None:
        rating = str(rating)
    regime = snapshot.get("regime_assumption")
    return {
        "status": status,
        "strategic_bias": bias,
        "conviction": float(snapshot.get("conviction") or 0.0),
        "accepted_rating": rating,
        "thesis": str(snapshot.get("thesis") or ""),
        "key_drivers": _as_list(snapshot.get("key_drivers")),
        "watch_conditions": _as_list(snapshot.get("watch_conditions")),
        "invalidation_conditions": _as_list(snapshot.get("invalidation_conditions")),
        "open_questions": _as_list(snapshot.get("open_questions")),
        "regime_assumption": _as_dict(regime),
        "time_horizon": snapshot.get("time_horizon") or None,
    }


def _timestamp(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _strength_value(value: object) -> float | None:
    mapping = {"none": 0.0, "minor": 0.25, "material": 0.65, "major": 1.0}
    if isinstance(value, str):
        return mapping.get(value.lower())
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, numeric))


def _safe_hold(decision: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    """Turn a stale action into HOLD/NO_NEW_ORDER without replaying old risk."""

    held = copy.deepcopy(dict(decision))
    held.update(
        {
            "rating": "Hold",
            "entry_price": None,
            "stop_loss": None,
            "take_profit_price": None,
            "position_size_pct": None,
            "suggested_capital": 0.0,
            "execution_action": "no_order",
            "stability_override_reason": reason,
        }
    )
    return held


def _with_conflict_transition(final_payload: dict[str, Any], *, reason: str) -> dict[str, Any]:
    transition = _mapping(final_payload.get("decision_transition_json"))
    transition["strategy_persistence_status"] = "conflict"
    transition["strategy_persistence_reason"] = reason
    transition["execution_action"] = "NO_NEW_ORDER"
    transition["outcome"] = "BLOCKED_CHANGE"
    return transition


def _candidate_parts(candidate_raw: object) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    candidate = _mapping(candidate_raw)
    before = _mapping(candidate.get("strategy_before")) or None
    after = _mapping(candidate.get("strategy_after")) or None
    return candidate, before, after


async def _create_with_conflict_handling(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    after: Mapping[str, Any],
    analysis_id: int,
    effective_at: datetime,
    candidate: Mapping[str, Any],
    pm_rating: str | None,
) -> tuple[object | None, bool]:
    """Create v1 within a savepoint so a concurrent initial run is safe."""

    try:
        async with db.begin_nested():
            strategy = await create_asset_strategy(
                db,
                user_id=user_id,
                ticker=ticker,
                asset_type=asset_type,
                state=_db_strategy_state(after),
                analysis_id=analysis_id,
                effective_at=effective_at,
                revision_action=str(candidate.get("revision_action") or "CREATE"),
                triggered_invalidations=_as_list(candidate.get("triggered_invalidations")),
                supporting_evidence=_as_list(candidate.get("supporting_evidence")),
                regime_before=_mapping(candidate.get("regime_before")) or None,
                regime_after=_mapping(candidate.get("regime_after")) or None,
                pm_proposed_rating=pm_rating,
                change_strength=_strength_value(candidate.get("change_strength")),
            )
        return strategy, False
    except IntegrityError:
        # The enclosing session remains usable because the failed create was
        # isolated in a savepoint.  Never convert this into an implicit retry;
        # callers must fail closed rather than apply a stale initial thesis.
        _logger.info("Concurrent AssetStrategy create detected for %s/%s", ticker, asset_type)
        return None, True


async def persist_completed_analysis_with_strategy(
    db: AsyncSession,
    *,
    row_id: int,
    final_payload: Mapping[str, Any],
    strategy_context: Mapping[str, Any] | None,
    candidate_raw: object,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    trade_date: str | datetime,
    learning_eligible: bool,
) -> StrategyPersistenceResult:
    """Persist an accepted analysis and optionally apply its strategy revision.

    The final commit happens exactly once, after the CAS/version append and
    ``AnalysisResult`` field assignment.  A stale CAS never causes an order to
    be emitted: the physical canonical decision is replaced with a HOLD and
    the caller can render the conflict in its transition card.
    """

    from backend.models.analysis import AnalysisResult

    row = await db.get(AnalysisResult, row_id, with_for_update=True)
    if row is None:
        raise ValueError("Analysis result no longer exists")

    payload = dict(final_payload)
    context = _mapping(strategy_context)
    candidate, candidate_before, candidate_after = _candidate_parts(candidate_raw)
    before_snapshot = _mapping(context.get("strategy_before")) or candidate_before
    before_version = before_snapshot.get("version") if before_snapshot else None
    effective_at = _timestamp(trade_date, datetime.now(UTC))
    proposed_decision = _mapping(payload.get("pm_proposal_json"))
    if "proposed_decision" in proposed_decision:
        proposed_decision = _mapping(proposed_decision.get("proposed_decision"))
    pm_rating = str(proposed_decision.get("rating") or "").strip() or None
    accepted_rating = str(_mapping(payload.get("portfolio_decision_json")).get("rating") or "").strip() or None
    # The reconciler intentionally runs before the PM so it cannot leak an old
    # rating to analysts. For a new lineage, bind the eventually accepted
    # tactical rating only at this post-controller persistence boundary.
    if (
        str(candidate.get("revision_action") or "").upper() in {"CREATE", "REBUILD"}
        and candidate_after is not None
        and accepted_rating
    ):
        candidate_after["accepted_rating"] = accepted_rating
        candidate["strategy_after"] = candidate_after

    status = "not_requested"
    strategy_id: int | None = None
    after_snapshot: dict[str, Any] | None = before_snapshot
    after_version = before_version
    decision_override: dict[str, Any] | None = None
    reason: str | None = None

    if not learning_eligible:
        status = "not_eligible"
        reason = "historical_or_time_travel_run"
    elif not candidate:
        status = "candidate_missing"
        reason = "strategy_reconciler_did_not_return_a_candidate"
    else:
        action = str(candidate.get("revision_action") or "").upper()
        expected_version = candidate.get("expected_version") or context.get("expected_version")
        strategy_id = context.get("strategy_id") or (candidate_before or {}).get("strategy_id")

        if action == "CREATE":
            if before_snapshot is not None or candidate_after is None:
                status = "candidate_invalid"
                reason = "CREATE requires a new after-state and no active prior strategy"
            else:
                strategy, conflict = await _create_with_conflict_handling(
                    db,
                    user_id=user_id,
                    ticker=ticker,
                    asset_type=asset_type,
                    after=candidate_after,
                    analysis_id=row_id,
                    effective_at=effective_at,
                    candidate=candidate,
                    pm_rating=pm_rating,
                )
                if conflict:
                    status = "conflict"
                    reason = "concurrent_strategy_create"
                else:
                    assert strategy is not None
                    status = "created"
                    strategy_id = strategy.id
                    after_snapshot = strategy_state_snapshot(strategy)
                    after_version = strategy.version

        elif action == "KEEP":
            if not isinstance(strategy_id, int) or not isinstance(expected_version, int):
                status = "candidate_invalid"
                reason = "KEEP requires strategy_id and expected_version"
            else:
                cas = await touch_asset_strategy_review(
                    db,
                    strategy_id=strategy_id,
                    expected_version=expected_version,
                    reviewed_at=effective_at,
                    analysis_id=row_id,
                )
                status, reason, strategy_id, after_snapshot, after_version = _apply_cas_result(cas, "reviewed")

        elif action in {"STRENGTHEN", "WEAKEN", "INVALIDATE"}:
            if not isinstance(strategy_id, int) or not isinstance(expected_version, int):
                status = "candidate_invalid"
                reason = f"{action} requires strategy_id and expected_version"
            else:
                updates = _db_strategy_state(candidate_after or before_snapshot or {})
                if action == "INVALIDATE" and candidate_after is None:
                    updates["status"] = "INVALIDATED"
                cas = await compare_and_swap_asset_strategy(
                    db,
                    strategy_id=strategy_id,
                    expected_version=expected_version,
                    updates=updates,
                    revision_action=action,
                    analysis_id=row_id,
                    effective_at=effective_at,
                    triggered_invalidations=_as_list(candidate.get("triggered_invalidations")),
                    supporting_evidence=_as_list(candidate.get("supporting_evidence")),
                    regime_before=_mapping(candidate.get("regime_before")) or None,
                    regime_after=_mapping(candidate.get("regime_after")) or None,
                    pm_proposed_rating=pm_rating,
                    change_strength=_strength_value(candidate.get("change_strength")),
                )
                status, reason, strategy_id, after_snapshot, after_version = _apply_cas_result(cas, "updated")

        elif action == "REBUILD":
            # Close the previous lineage through CAS before inserting v1 of the
            # replacement.  The two actions share the surrounding transaction,
            # so no reader sees a half-completed rebuild after a failure.
            predecessor_status = str((before_snapshot or {}).get("status") or "").upper()
            if predecessor_status not in {"INVALIDATED", "CLOSED"}:
                # The graph schema enforces this too, but persistence is the
                # authoritative write boundary.  A stale/corrupted checkpoint
                # or extension must not be able to close an ACTIVE lineage by
                # bypassing Pydantic validation.
                status = "candidate_invalid"
                reason = "REBUILD requires an INVALIDATED or CLOSED predecessor"
            elif not isinstance(strategy_id, int) or not isinstance(expected_version, int) or candidate_after is None:
                status = "candidate_invalid"
                reason = "REBUILD requires previous lineage, expected_version, and replacement after-state"
            else:
                # One savepoint covers *both* closing the old lineage and
                # creating the replacement.  If the insert races/fails, the
                # old ACTIVE row is restored rather than leaving the ticker
                # with no current strategy.
                try:
                    async with db.begin_nested():
                        cas = await compare_and_swap_asset_strategy(
                            db,
                            strategy_id=strategy_id,
                            expected_version=expected_version,
                            updates={"status": "CLOSED"},
                            revision_action="REBUILD",
                            analysis_id=row_id,
                            effective_at=effective_at,
                            triggered_invalidations=_as_list(candidate.get("triggered_invalidations")),
                            supporting_evidence=_as_list(candidate.get("supporting_evidence")),
                            regime_before=_mapping(candidate.get("regime_before")) or None,
                            regime_after=_mapping(candidate.get("regime_after")) or None,
                            pm_proposed_rating=pm_rating,
                            change_strength=_strength_value(candidate.get("change_strength")),
                        )
                        if cas.conflict or not cas.applied:
                            status, reason, strategy_id, after_snapshot, after_version = _apply_cas_result(cas, "rebuilt")
                        else:
                            strategy = await create_asset_strategy(
                                db,
                                user_id=user_id,
                                ticker=ticker,
                                asset_type=asset_type,
                                state=_db_strategy_state(candidate_after),
                                analysis_id=row_id,
                                effective_at=effective_at,
                                revision_action="REBUILD",
                                triggered_invalidations=_as_list(candidate.get("triggered_invalidations")),
                                supporting_evidence=_as_list(candidate.get("supporting_evidence")),
                                regime_before=_mapping(candidate.get("regime_before")) or None,
                                regime_after=_mapping(candidate.get("regime_after")) or None,
                                pm_proposed_rating=pm_rating,
                                change_strength=_strength_value(candidate.get("change_strength")),
                            )
                            status = "rebuilt"
                            strategy_id = strategy.id
                            after_snapshot = strategy_state_snapshot(strategy)
                            after_version = strategy.version
                except IntegrityError:
                    status = "conflict"
                    reason = "concurrent_strategy_rebuild"
        else:
            status = "candidate_invalid"
            reason = f"unsupported_revision_action:{action or 'missing'}"

    if status == "conflict":
        existing = _mapping(payload.get("portfolio_decision_json"))
        decision_override = _safe_hold(existing, reason=reason or "strategy_conflict")
        payload["portfolio_decision_json"] = decision_override
        # Older readers can still consult the annotation copy. Keep it aligned
        # with the physical canonical decision so a stale PM proposal is never
        # rendered as an executable recommendation after a CAS conflict.
        annotations = _mapping(payload.get("chart_annotations"))
        annotations["portfolio_decision"] = copy.deepcopy(decision_override)
        payload["chart_annotations"] = annotations
        payload["signal"] = "Hold"
        payload["final_decision"] = (
            "Hold — no new order: this analysis used a stale Asset Strategy version and was not applied."
        )
        payload["decision_transition_json"] = _with_conflict_transition(payload, reason=reason or "strategy_conflict")

    payload.update(
        {
            "status": "completed",
            "strategy_id": strategy_id,
            "strategy_before_json": before_snapshot,
            "strategy_after_json": after_snapshot,
            "strategy_candidate_json": candidate or None,
            "strategy_update_status": status,
            "strategy_before_version": before_version,
            "strategy_after_version": after_version,
        }
    )
    for key, value in payload.items():
        if hasattr(row, key):
            setattr(row, key, value)
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise

    return StrategyPersistenceResult(
        status=status,
        strategy_id=strategy_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        before_version=before_version,
        after_version=after_version,
        decision_override=decision_override,
        reason=reason,
    )


def _apply_cas_result(
    cas: AssetStrategyCASResult,
    success_status: str,
) -> tuple[str, str | None, int | None, dict[str, Any] | None, int | None]:
    if cas.applied and cas.strategy is not None:
        snapshot = strategy_state_snapshot(cas.strategy)
        return success_status, None, cas.strategy.id, snapshot, cas.strategy.version
    if cas.conflict:
        snapshot = strategy_state_snapshot(cas.strategy) if cas.strategy is not None else None
        return "conflict", "expected_version_mismatch", cas.strategy.id if cas.strategy else None, snapshot, (
            cas.actual_version
        )
    return "not_found", "strategy_not_found", None, None, None


__all__ = ["StrategyPersistenceResult", "persist_completed_analysis_with_strategy"]
