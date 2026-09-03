"""Compare fresh structured evidence with the persistent asset strategy.

This node may propose only a strategy lifecycle transition.  It does not place
an order, size a position, or persist anything; the Portfolio Manager proposes
the tactical action later and the deterministic controller/persistence layer
decides whether either change becomes canonical.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import (
    AssetStrategySnapshot,
    AssetStrategyStatus,
    DataQualityLevel,
    EvidenceItem,
    InvalidationCondition,
    InvalidationKind,
    InvalidationSeverity,
    InvalidationStatus,
    PortfolioRating,
    ResearchBias,
    StrategyChangeStrength,
    StrategyRevisionAction,
    StrategyRevisionCandidate,
    StructuredAgentSchema,
)
from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

logger = logging.getLogger(__name__)

MAIN_KEY = "strategy_reconciler"


class StrategyRevisionIntent(StructuredAgentSchema):
    """Small LLM-facing decision contract materialized into exact state in code.

    The model chooses the lifecycle action and explains why.  It deliberately
    does not reproduce ``strategy_before`` / ``strategy_after`` or choose a raw
    conviction value; those fields are derived from canonical state so semantic
    invariants cannot be broken by a malformed structured completion.
    """

    revision_action: StrategyRevisionAction
    change_strength: StrategyChangeStrength
    revision_reason: str = Field(min_length=1)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _snapshot_from_raw(raw: object) -> AssetStrategySnapshot | None:
    values = _mapping(raw)
    if not values:
        return None
    values.pop("user_id", None)
    values.pop("recorded_at", None)
    try:
        return AssetStrategySnapshot.model_validate(values)
    except Exception as exc:
        logger.warning("Ignoring malformed persistent AssetStrategy snapshot: %s", exc)
        return None


def _evidence_items(synthesis: Mapping[str, Any]) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    groups = synthesis.get("evidence_groups")
    if not isinstance(groups, Mapping):
        return out
    for items in groups.values():
        if not isinstance(items, list):
            continue
        for raw in items:
            try:
                out.append(EvidenceItem.model_validate(raw))
            except Exception:
                continue
    return out


def _invalidations_from_plan(state: Mapping[str, Any]) -> list[InvalidationCondition]:
    plan = _mapping(state.get("analysis_plan_json"))
    raw_items = plan.get("invalidations_to_check")
    if not isinstance(raw_items, list):
        return []
    values: list[InvalidationCondition] = []
    for raw in raw_items:
        try:
            values.append(InvalidationCondition.model_validate(raw))
        except Exception:
            continue
    return values


def _default_invalidation() -> InvalidationCondition:
    return InvalidationCondition(
        condition_id="core_evidence_deterioration",
        statement="Multiple independent core evidence sources deteriorate materially.",
        kind=InvalidationKind.QUALITATIVE,
        severity=InvalidationSeverity.MATERIAL,
        qualitative_criteria="Two independent evidence groups identify a material deterioration in the core thesis.",
        status=InvalidationStatus.NOT_EVALUATED,
    )


def _quality_is_high(synthesis: Mapping[str, Any]) -> bool:
    quality = _mapping(synthesis.get("data_quality"))
    level = str(quality.get("level") or "").lower()
    try:
        score = float(quality.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return level == DataQualityLevel.HIGH.value or score >= 80.0


def _bias(value: object, default: ResearchBias = ResearchBias.NEUTRAL) -> ResearchBias:
    try:
        return ResearchBias(str(value).capitalize())
    except ValueError:
        return default


def _material_invalidations(raw: object) -> list[dict[str, Any]]:
    """Return only validated invalidations strong enough to close a thesis."""
    if not isinstance(raw, list):
        return []
    return [
        item
        for item in raw
        if isinstance(item, dict)
        and str(item.get("severity") or "").strip().lower() in {
            InvalidationSeverity.MATERIAL.value,
            InvalidationSeverity.CRITICAL.value,
        }
    ]


def _next_snapshot(
    before: AssetStrategySnapshot,
    *,
    action: StrategyRevisionAction,
    conviction: float | None = None,
    status: AssetStrategyStatus | None = None,
) -> AssetStrategySnapshot:
    updates: dict[str, Any] = {
        "version": before.version if action is StrategyRevisionAction.KEEP else before.version + 1,
        "last_reviewed_at": datetime.now(UTC),
    }
    if conviction is not None:
        updates["conviction"] = round(min(1.0, max(0.0, conviction)), 4)
    if status is not None:
        updates["status"] = status
    return before.model_copy(update=updates)


def _fallback_candidate(state: Mapping[str, Any]) -> StrategyRevisionCandidate:
    context = _mapping(state.get("strategy_context"))
    before = _snapshot_from_raw(context.get("strategy_before"))
    synthesis = _mapping(state.get("synthesis_json"))
    evidence = _evidence_items(synthesis)
    triggered_raw = synthesis.get("triggered_invalidations")
    triggered = triggered_raw if isinstance(triggered_raw, list) else []
    material_triggered = _material_invalidations(triggered)
    ticker = str(state.get("company_of_interest") or "UNKNOWN").upper()
    asset_type = str(state.get("asset_type") or "stock").lower()

    if before is None:
        plan_invalidations = _invalidations_from_plan(state)
        drivers = [item.claim for item in evidence[:3]] or ["Fresh multi-source evidence must be reviewed."]
        after = AssetStrategySnapshot(
            strategy_id=None,
            ticker=ticker,
            asset_type=asset_type,
            status=AssetStrategyStatus.ACTIVE,
            version=1,
            strategic_bias=_bias(synthesis.get("dominant_bias")),
            conviction=0.5,
            accepted_rating=PortfolioRating.HOLD,
            thesis="Initial exact strategy created from the current independently gathered evidence.",
            key_drivers=drivers,
            watch_conditions=["Validate evidence coverage on the next review."],
            invalidation_conditions=plan_invalidations or [_default_invalidation()],
            open_questions=list(synthesis.get("unresolved_questions") or [])[:5],
            regime_assumption=_mapping(synthesis.get("market_regime")) or None,
            time_horizon="current analysis horizon",
            effective_at=datetime.now(UTC),
        )
        return StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.CREATE,
            expected_version=None,
            strategy_before=None,
            strategy_after=after,
            change_strength=StrategyChangeStrength.MATERIAL,
            revision_reason="No exact prior strategy exists; create an initial baseline after independent research.",
            supporting_evidence=evidence[:8],
            triggered_invalidations=triggered,
            regime_before=None,
            regime_after=after.regime_assumption,
        )

    if before.status in {AssetStrategyStatus.INVALIDATED, AssetStrategyStatus.CLOSED}:
        plan_invalidations = _invalidations_from_plan(state)
        drivers = [item.claim for item in evidence[:3]] or ["Fresh replacement evidence must be revalidated."]
        replacement_bias = _bias(synthesis.get("dominant_bias"), ResearchBias.NEUTRAL)
        replacement_regime = _mapping(synthesis.get("market_regime")) or None
        after = AssetStrategySnapshot(
            strategy_id=None,
            ticker=before.ticker,
            asset_type=before.asset_type,
            status=AssetStrategyStatus.ACTIVE,
            version=1,
            strategic_bias=replacement_bias,
            conviction=0.6 if _quality_is_high(synthesis) and len(evidence) >= 4 else 0.5,
            accepted_rating=PortfolioRating.HOLD,
            thesis="Replacement exact strategy created after the prior thesis was invalidated or closed.",
            key_drivers=drivers,
            watch_conditions=["Independently revalidate the replacement thesis on the next review."],
            invalidation_conditions=plan_invalidations or before.invalidation_conditions or [_default_invalidation()],
            open_questions=list(synthesis.get("unresolved_questions") or [])[:5],
            regime_assumption=replacement_regime,
            time_horizon=before.time_horizon or "current analysis horizon",
            effective_at=datetime.now(UTC),
        )
        return StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.REBUILD,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=StrategyChangeStrength.MAJOR,
            revision_reason="The prior lineage is no longer active; establish a separately auditable replacement thesis.",
            supporting_evidence=evidence[:8],
            triggered_invalidations=material_triggered,
            regime_before=before.regime_assumption,
            regime_after=after.regime_assumption,
        )

    dominant = _bias(synthesis.get("dominant_bias"), before.strategic_bias)
    if material_triggered:
        after = _next_snapshot(
            before,
            action=StrategyRevisionAction.INVALIDATE,
            status=AssetStrategyStatus.INVALIDATED,
        )
        return StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.INVALIDATE,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=StrategyChangeStrength.MAJOR,
            revision_reason="Validated material/critical synthesis evidence triggered an explicit strategy invalidation.",
            supporting_evidence=evidence[:8],
            triggered_invalidations=material_triggered,
            regime_before=before.regime_assumption,
            regime_after=_mapping(synthesis.get("market_regime")) or before.regime_assumption,
        )

    if dominant is not before.strategic_bias:
        if before.conviction > 0.0:
            after = _next_snapshot(
                before,
                action=StrategyRevisionAction.WEAKEN,
                conviction=before.conviction - 0.10,
            )
            return StrategyRevisionCandidate(
                revision_action=StrategyRevisionAction.WEAKEN,
                expected_version=before.version,
                strategy_before=before,
                strategy_after=after,
                change_strength=StrategyChangeStrength.MATERIAL,
                revision_reason="Fresh structured synthesis differs from the active strategic bias; retain the same thesis direction with lower conviction until explicit invalidation is established.",
                supporting_evidence=evidence[:8],
                triggered_invalidations=[],
                regime_before=before.regime_assumption,
                regime_after=_mapping(synthesis.get("market_regime")) or before.regime_assumption,
            )

        # There is no lower legal conviction than zero.  Keep the current
        # lineage unchanged until an evidence-backed invalidation is triggered;
        # never fall through and strengthen a thesis that the synthesis opposes.
        after = _next_snapshot(before, action=StrategyRevisionAction.KEEP)
        return StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.KEEP,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=StrategyChangeStrength.NONE,
            revision_reason="Fresh synthesis opposes the active bias, but conviction is already zero; retain the lineage unchanged until an explicit invalidation is established.",
            supporting_evidence=evidence[:8],
            triggered_invalidations=[],
            regime_before=before.regime_assumption,
            regime_after=_mapping(synthesis.get("market_regime")) or before.regime_assumption,
        )

    if _quality_is_high(synthesis) and len(evidence) >= 4 and before.conviction <= 0.85:
        after = _next_snapshot(
            before,
            action=StrategyRevisionAction.STRENGTHEN,
            conviction=before.conviction + 0.05,
        )
        return StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.STRENGTHEN,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=StrategyChangeStrength.MATERIAL,
            revision_reason="High-quality, multi-source evidence materially reinforces the active thesis.",
            supporting_evidence=evidence[:8],
            triggered_invalidations=[],
            regime_before=before.regime_assumption,
            regime_after=_mapping(synthesis.get("market_regime")) or before.regime_assumption,
        )

    after = _next_snapshot(before, action=StrategyRevisionAction.KEEP)
    return StrategyRevisionCandidate(
        revision_action=StrategyRevisionAction.KEEP,
        expected_version=before.version,
        strategy_before=before,
        strategy_after=after,
        change_strength=StrategyChangeStrength.NONE,
        revision_reason="No material evidence delta justified revising the active strategy.",
        supporting_evidence=evidence[:8],
        triggered_invalidations=[],
        regime_before=before.regime_assumption,
        regime_after=_mapping(synthesis.get("market_regime")) or before.regime_assumption,
    )


def _materialize_intent(
    state: Mapping[str, Any],
    intent: StrategyRevisionIntent,
    fallback: StrategyRevisionCandidate,
) -> StrategyRevisionCandidate:
    """Turn a small LLM intent into a schema-valid exact transition.

    Lifecycle state, versions, evidence and conviction arithmetic remain under
    deterministic control.  If an intent is impossible for the current state,
    the already validated fallback is returned instead of asking the model to
    reproduce canonical snapshots correctly.
    """

    context = _mapping(state.get("strategy_context"))
    before = _snapshot_from_raw(context.get("strategy_before"))
    synthesis = _mapping(state.get("synthesis_json"))
    evidence = _evidence_items(synthesis)
    material_triggered = _material_invalidations(synthesis.get("triggered_invalidations"))
    action = intent.revision_action

    if before is None:
        if action is StrategyRevisionAction.CREATE:
            return fallback.model_copy(update={"revision_reason": intent.revision_reason})
        return fallback

    if before.status in {AssetStrategyStatus.INVALIDATED, AssetStrategyStatus.CLOSED}:
        if action is StrategyRevisionAction.REBUILD:
            return fallback.model_copy(update={"revision_reason": intent.revision_reason})
        return fallback

    if action in {StrategyRevisionAction.CREATE, StrategyRevisionAction.REBUILD}:
        return fallback

    regime_after = _mapping(synthesis.get("market_regime")) or before.regime_assumption

    if action is StrategyRevisionAction.INVALIDATE:
        if not material_triggered:
            return fallback
        after = _next_snapshot(
            before,
            action=StrategyRevisionAction.INVALIDATE,
            status=AssetStrategyStatus.INVALIDATED,
        )
        return StrategyRevisionCandidate(
            revision_action=action,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=StrategyChangeStrength.MAJOR,
            revision_reason=intent.revision_reason,
            supporting_evidence=evidence[:8],
            triggered_invalidations=material_triggered,
            regime_before=before.regime_assumption,
            regime_after=regime_after,
        )

    if action is StrategyRevisionAction.KEEP:
        after = _next_snapshot(before, action=action)
        strength = (
            StrategyChangeStrength.MINOR
            if intent.change_strength is StrategyChangeStrength.MINOR
            else StrategyChangeStrength.NONE
        )
        return StrategyRevisionCandidate(
            revision_action=action,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=strength,
            revision_reason=intent.revision_reason,
            supporting_evidence=evidence[:8],
            triggered_invalidations=[],
            regime_before=before.regime_assumption,
            regime_after=regime_after,
        )

    if action in {StrategyRevisionAction.STRENGTHEN, StrategyRevisionAction.WEAKEN}:
        dominant = _bias(synthesis.get("dominant_bias"), before.strategic_bias)
        if action is StrategyRevisionAction.STRENGTHEN and dominant is not before.strategic_bias:
            return fallback
        if action is StrategyRevisionAction.WEAKEN and before.conviction <= 0.0:
            return fallback
        if action is StrategyRevisionAction.STRENGTHEN and before.conviction >= 1.0:
            return fallback

        # The model chooses direction and materiality, never the numeric value.
        # This makes the strict Pydantic invariants true by construction.
        strength = (
            intent.change_strength
            if intent.change_strength in {StrategyChangeStrength.MATERIAL, StrategyChangeStrength.MAJOR}
            else StrategyChangeStrength.MATERIAL
        )
        delta = 0.10 if strength is StrategyChangeStrength.MAJOR else 0.05
        conviction = before.conviction + delta if action is StrategyRevisionAction.STRENGTHEN else before.conviction - delta
        after = _next_snapshot(before, action=action, conviction=conviction)
        return StrategyRevisionCandidate(
            revision_action=action,
            expected_version=before.version,
            strategy_before=before,
            strategy_after=after,
            change_strength=strength,
            revision_reason=intent.revision_reason,
            supporting_evidence=evidence[:8],
            triggered_invalidations=[],
            regime_before=before.regime_assumption,
            regime_after=regime_after,
        )

    return fallback


def _candidate_respects_lifecycle(candidate: StrategyRevisionCandidate, state: Mapping[str, Any]) -> bool:
    """Reject LLM candidates that bypass deterministic lifecycle invariants."""
    before = candidate.strategy_before
    after = candidate.strategy_after
    synthesis = _mapping(state.get("synthesis_json"))
    allowed_invalidations = _material_invalidations(synthesis.get("triggered_invalidations"))
    allowed_ids = {str(item.get("condition_id")) for item in allowed_invalidations}

    if candidate.revision_action is StrategyRevisionAction.INVALIDATE:
        candidate_ids = {item.condition_id for item in candidate.triggered_invalidations}
        if not candidate_ids or not candidate_ids.issubset(allowed_ids):
            return False

    if candidate.revision_action in {StrategyRevisionAction.STRENGTHEN, StrategyRevisionAction.WEAKEN}:
        if before is None or after is None:
            return False
        if before.status is not AssetStrategyStatus.ACTIVE or after.status is not AssetStrategyStatus.ACTIVE:
            return False
        if after.strategic_bias is not before.strategic_bias:
            return False
        if after.accepted_rating is not before.accepted_rating:
            return False

    if candidate.revision_action in {StrategyRevisionAction.CREATE, StrategyRevisionAction.REBUILD}:
        if after is None or after.status is not AssetStrategyStatus.ACTIVE:
            return False

    return True


def _render_candidate(candidate: StrategyRevisionCandidate) -> str:
    before = candidate.strategy_before
    after = candidate.strategy_after
    return "\n".join(
        [
            "## Strategy Reconciliation",
            "",
            f"**Action:** {candidate.revision_action.value}",
            f"**Change strength:** {candidate.change_strength.value}",
            f"**Reason:** {candidate.revision_reason}",
            f"**Version:** {before.version if before else 'none'} → {after.version if after else 'closed'}",
        ]
    )


def create_strategy_reconciler_node(ctx: AgentRunContext) -> NodeFn:
    async def strategy_reconciler_node(state: dict) -> dict:
        fallback = _fallback_candidate(state)
        if not ctx.is_enabled(MAIN_KEY):
            return {
                "strategy_candidate_json": fallback.model_dump(mode="json"),
                "strategy_reconciliation_report": _render_candidate(fallback),
            }

        prompt = f"""You are a strategy reconciler. Compare an exact active asset strategy with
fresh structured evidence, research, and risk guardrails. Return only a
StrategyRevisionIntent matching the schema. Do NOT reproduce strategy_before,
strategy_after, versions, or numeric conviction values; the caller materializes
those fields deterministically from canonical state.

## Existing strategy context
{json.dumps(_mapping(state.get('strategy_context')).get('strategy_before'), ensure_ascii=False, default=str)}

## Structured synthesis
{json.dumps(_mapping(state.get('synthesis_json')), ensure_ascii=False, default=str)}

## Research plan
{state.get('investment_plan') or ''}

## Risk debate
{_mapping(state.get('risk_debate_state')).get('history', '')}

Rules:
- Choose only CREATE, KEEP, STRENGTHEN, WEAKEN, INVALIDATE, or REBUILD.
- KEEP means conviction stays unchanged.
- WEAKEN means conviction must strictly decrease; never choose WEAKEN when current conviction is already 0.
- STRENGTHEN means conviction must strictly increase; never choose STRENGTHEN when current conviction is already 1 or when Structured Synthesis has a different dominant_bias than the active strategy.
- For STRENGTHEN/WEAKEN, use MATERIAL or MAJOR change_strength. The caller computes the exact numeric conviction delta.
- STRENGTHEN/WEAKEN preserve ACTIVE status, strategic_bias, accepted_rating, ticker, asset type and lineage. A direction change requires INVALIDATE followed by a later REBUILD.
- INVALIDATE requires a validated MATERIAL or CRITICAL triggered invalidation from Structured Synthesis. WATCH conditions can justify caution/WEAKEN but never close a thesis.
- CREATE is only valid when there is no prior strategy. REBUILD is only valid when the prior strategy is INVALIDATED or CLOSED.
- Do not emit Buy, Sell, order sizing, entries, stops, or execution advice.
- Review-origin evidence never counts as independent reversal confirmation.
{get_general_settings_block()}"""
        try:
            result = await ainvoke_structured_or_freetext(
                bind_structured(ctx.llm_for(MAIN_KEY), StrategyRevisionIntent, "Strategy Reconciler"),
                ctx.llm_for(MAIN_KEY),
                prompt,
                "Strategy Reconciler",
                schema=StrategyRevisionIntent,
            )
            candidate = (
                _materialize_intent(state, result, fallback)
                if isinstance(result, StrategyRevisionIntent)
                else fallback
            )
            if not _candidate_respects_lifecycle(candidate, state):
                logger.warning("Strategy reconciler candidate violated deterministic lifecycle invariants; using fallback")
                candidate = fallback
        except Exception as exc:  # noqa: BLE001 - fallback retains safe strategy invariants
            logger.warning("Strategy reconciler failed: %s", exc)
            candidate = fallback
        return {
            "strategy_candidate_json": candidate.model_dump(mode="json"),
            "strategy_reconciliation_report": _render_candidate(candidate),
        }

    return strategy_reconciler_node


__all__ = ["StrategyRevisionIntent", "create_strategy_reconciler_node"]
