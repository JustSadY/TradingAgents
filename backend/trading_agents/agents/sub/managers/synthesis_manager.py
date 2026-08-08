"""Human-readable and structured synthesis of the independent analyst reports."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import (
    AnalystEvidenceAssessment,
    DataQualityAssessment,
    DataQualityLevel,
    EvidenceCoverage,
    EvidenceGroup,
    EvidenceItem,
    EvidenceSourceFamily,
    EvidenceStrength,
    InvalidationSeverity,
    MacroRegime,
    MarketRegimeSnapshot,
    MarketTrend,
    ResearchBias,
    RiskRegime,
    SynthesisAssessment,
    VolatilityRegime,
)
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_system_instruction_override,
    run_macd_rsi_backtests,
)

_logger = logging.getLogger(__name__)

_TEAM_BY_ANALYST = {
    "market": EvidenceGroup.TECHNICAL,
    "quant": EvidenceGroup.TECHNICAL,
    "fundamentals": EvidenceGroup.FUNDAMENTAL,
    "earnings": EvidenceGroup.FUNDAMENTAL,
    "insider": EvidenceGroup.FUNDAMENTAL,
    "ownership": EvidenceGroup.FUNDAMENTAL,
    "ratings": EvidenceGroup.FUNDAMENTAL,
    "short_interest": EvidenceGroup.FUNDAMENTAL,
    "valuation": EvidenceGroup.FUNDAMENTAL,
    "macro": EvidenceGroup.MACRO_SENTIMENT,
    "social": EvidenceGroup.MACRO_SENTIMENT,
    "news": EvidenceGroup.MACRO_SENTIMENT,
    "options": EvidenceGroup.CATALYST_OPTIONS,
    "catalyst": EvidenceGroup.CATALYST_OPTIONS,
    "review": EvidenceGroup.REVIEW,
}
_FAMILY_BY_ANALYST = {
    "market": EvidenceSourceFamily.MARKET_DATA,
    "quant": EvidenceSourceFamily.MODEL_DERIVED,
    "fundamentals": EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
    "earnings": EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
    "insider": EvidenceSourceFamily.INSTITUTIONAL,
    "ownership": EvidenceSourceFamily.INSTITUTIONAL,
    "ratings": EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
    "short_interest": EvidenceSourceFamily.MARKET_DATA,
    "valuation": EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
    "macro": EvidenceSourceFamily.MACROECONOMIC,
    "social": EvidenceSourceFamily.NEWS,
    "news": EvidenceSourceFamily.NEWS,
    "options": EvidenceSourceFamily.DERIVATIVES,
    "catalyst": EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
    "review": EvidenceSourceFamily.INTERNAL_REVIEW,
}
_POSITIVE = ("bullish", "positive", "upside", "growth", "improv", "accumulat", "outperform")
_NEGATIVE = ("bearish", "negative", "downside", "deteriorat", "declin", "risk-off", "cut")
_UNAVAILABLE = ("unavailable", "failed", "no data", "not available")


def _analyst_key(report_key: str) -> str:
    from backend.trading_agents.agents.analyst_registry import analyst_key_for_report

    return analyst_key_for_report(report_key) or report_key.removesuffix("_report")


def _bias_from_text(text: str) -> ResearchBias:
    lowered = text.lower()
    positive = sum(lowered.count(token) for token in _POSITIVE)
    negative = sum(lowered.count(token) for token in _NEGATIVE)
    if positive > negative:
        return ResearchBias.BULLISH
    if negative > positive:
        return ResearchBias.BEARISH
    return ResearchBias.NEUTRAL


def _fallback_regime(macro_report: str) -> MarketRegimeSnapshot:
    text = macro_report.lower()
    risk = RiskRegime.RISK_OFF if "risk-off" in text or "risk off" in text else RiskRegime.RISK_ON if "risk-on" in text or "risk on" in text else RiskRegime.NEUTRAL
    trend = MarketTrend.BEAR if "bearish" in text else MarketTrend.BULL if "bullish" in text else MarketTrend.UNCERTAIN
    volatility = VolatilityRegime.HIGH if "high volatility" in text else VolatilityRegime.ELEVATED if "elevated volatility" in text else VolatilityRegime.NORMAL
    macro = MacroRegime.CONTRACTION if "contraction" in text else MacroRegime.LATE_EXPANSION if "late expansion" in text else MacroRegime.UNCERTAIN
    return MarketRegimeSnapshot(
        trend=trend,
        volatility=volatility,
        risk=risk,
        macro=macro,
        confidence=0.35 if macro_report.strip() else 0.15,
    )


def _plan_invalidation_catalog(state: dict) -> dict[str, dict]:
    """Return the only invalidation conditions synthesis is allowed to trigger."""
    plan = state.get("analysis_plan_json")
    if not isinstance(plan, dict):
        return {}
    raw = plan.get("invalidations_to_check")
    if not isinstance(raw, list):
        return {}
    catalog: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        condition_id = str(item.get("condition_id") or "").strip()
        if condition_id:
            catalog[condition_id] = item
    return catalog


def _sanitize_triggered_invalidations(state: dict, assessment: SynthesisAssessment) -> SynthesisAssessment:
    """Drop hallucinated/weak invalidations before they can affect strategy state.

    A synthesis model may only trigger a condition that the neutral AnalysisPlan
    explicitly asked the analysts to test. The severity comes from that plan,
    never from the synthesis model. At least one cited evidence item must be
    explicitly linked to the condition; critical invalidations additionally need
    two independent non-review evidence groups. This is a deterministic trust
    boundary: unknown IDs or unlinked evidence are observations, not events.
    """
    catalog = _plan_invalidation_catalog(state)
    if not catalog or not assessment.triggered_invalidations:
        if assessment.triggered_invalidations and not catalog:
            _logger.warning("Dropping synthesis invalidations because no AnalysisPlan invalidation catalog exists")
        return assessment.model_copy(update={"triggered_invalidations": []}) if assessment.triggered_invalidations else assessment

    evidence_by_id: dict[str, EvidenceItem] = {}
    for items in assessment.evidence_groups.values():
        for evidence in items:
            evidence_by_id[evidence.evidence_id] = evidence

    validated = []
    for invalidation in assessment.triggered_invalidations:
        condition = catalog.get(invalidation.condition_id)
        if condition is None:
            _logger.warning("Dropping unknown triggered invalidation id=%s", invalidation.condition_id)
            continue
        try:
            severity = InvalidationSeverity(str(condition.get("severity") or "material").lower())
        except ValueError:
            _logger.warning("Dropping invalidation %s with invalid plan severity", invalidation.condition_id)
            continue

        cited = [evidence_by_id[eid] for eid in invalidation.evidence_ids if eid in evidence_by_id]
        linked = [
            item
            for item in cited
            if invalidation.condition_id in item.related_invalidation_ids
        ]
        if not linked:
            _logger.warning("Dropping invalidation %s without explicitly linked evidence", invalidation.condition_id)
            continue

        independent_groups = {
            item.evidence_group
            for item in linked
            if item.independent_for_reversal and item.evidence_group is not EvidenceGroup.REVIEW
        }
        required_groups = 2 if severity is InvalidationSeverity.CRITICAL else 1
        if len(independent_groups) < required_groups:
            _logger.warning(
                "Dropping invalidation %s: independent evidence groups %d < %d",
                invalidation.condition_id,
                len(independent_groups),
                required_groups,
            )
            continue

        validated.append(
            invalidation.model_copy(
                update={
                    "severity": severity,
                    "evidence_ids": [item.evidence_id for item in linked],
                }
            )
        )

    return assessment.model_copy(update={"triggered_invalidations": validated})


def _deterministic_assessment(state: dict) -> SynthesisAssessment:
    from backend.services.analysis.reports import report_text
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    groups: dict[EvidenceGroup, list[EvidenceItem]] = defaultdict(list)
    analysts: list[AnalystEvidenceAssessment] = []
    all_biases: list[ResearchBias] = []
    missing_groups: set[EvidenceGroup] = set()
    for report_key in get_report_fields():
        analyst = _analyst_key(report_key)
        group = _TEAM_BY_ANALYST.get(analyst, EvidenceGroup.OTHER)
        family = _FAMILY_BY_ANALYST.get(analyst, EvidenceSourceFamily.OTHER)
        text = report_text(state.get(report_key))
        unavailable = not text or any(marker in text.lower() for marker in _UNAVAILABLE)
        if unavailable:
            missing_groups.add(group)
            analysts.append(
                AnalystEvidenceAssessment(
                    analyst=analyst,
                    evidence_group=group,
                    bias=ResearchBias.NEUTRAL,
                    evidence_strength=EvidenceStrength.NONE,
                    coverage=EvidenceCoverage.UNAVAILABLE,
                    evidence_ids=[],
                )
            )
            continue
        bias = _bias_from_text(text)
        strength = EvidenceStrength.MODERATE if len(text) >= 600 else EvidenceStrength.WEAK
        evidence_id = f"{analyst}_report"
        item = EvidenceItem(
            evidence_id=evidence_id,
            analyst=analyst,
            evidence_group=group,
            bias=bias,
            evidence_strength=strength,
            claim=text[:600],
            source_family=family,
            independent_for_reversal=group is not EvidenceGroup.REVIEW,
        )
        groups[group].append(item)
        analysts.append(
            AnalystEvidenceAssessment(
                analyst=analyst,
                evidence_group=group,
                bias=bias,
                evidence_strength=strength,
                coverage=EvidenceCoverage.AVAILABLE,
                evidence_ids=[evidence_id],
            )
        )
        all_biases.append(bias)

    if not analysts or not groups:
        placeholder = EvidenceItem(
            evidence_id="synthesis_no_verified_evidence",
            analyst="synthesis_manager",
            evidence_group=EvidenceGroup.OTHER,
            bias=ResearchBias.NEUTRAL,
            evidence_strength=EvidenceStrength.NONE,
            claim="No verified analyst evidence was available for structured synthesis.",
            source_family=EvidenceSourceFamily.OTHER,
            independent_for_reversal=False,
        )
        groups[EvidenceGroup.OTHER].append(placeholder)
        analysts = [
            AnalystEvidenceAssessment(
                analyst="synthesis_manager",
                evidence_group=EvidenceGroup.OTHER,
                bias=ResearchBias.NEUTRAL,
                evidence_strength=EvidenceStrength.NONE,
                coverage=EvidenceCoverage.UNAVAILABLE,
                evidence_ids=[],
            )
        ]
        missing_groups.add(EvidenceGroup.OTHER)

    bullish = all_biases.count(ResearchBias.BULLISH)
    bearish = all_biases.count(ResearchBias.BEARISH)
    dominant = ResearchBias.BULLISH if bullish > bearish else ResearchBias.BEARISH if bearish > bullish else ResearchBias.NEUTRAL
    available = list(groups.keys())
    score = min(100.0, round(100.0 * len(available) / max(1, len(set(_TEAM_BY_ANALYST.values()))), 1))
    level = DataQualityLevel.HIGH if score >= 75 else DataQualityLevel.MEDIUM if score >= 40 else DataQualityLevel.LOW
    return SynthesisAssessment(
        dominant_bias=dominant,
        analysts=analysts,
        evidence_groups=dict(groups),
        alignments=[],
        conflicts=[],
        triggered_invalidations=[],
        unresolved_questions=[],
        data_quality=DataQualityAssessment(
            level=level,
            score=score,
            available_evidence_groups=available,
            unavailable_evidence_groups=list(missing_groups - set(available)),
            known_gaps=[],
        ),
        market_regime=_fallback_regime(report_text(state.get("macro_report"))),
    )


def _render_assessment(assessment: SynthesisAssessment) -> str:
    lines = [
        "## Executive Synthesis Summary",
        "",
        f"- Dominant evidence posture: **{assessment.dominant_bias.value}**.",
        f"- Data quality: **{assessment.data_quality.level.value}** ({assessment.data_quality.score:.0f}/100).",
    ]
    if assessment.market_regime:
        regime = assessment.market_regime
        lines.append(
            f"- Market regime: **{regime.risk.value} / {regime.volatility.value} / {regime.macro.value}**."
        )
    lines.extend(["", "## Data Synthesis Table", "", "| Evidence group | Evidence count |", "|---|---:|"])
    for group, evidence in assessment.evidence_groups.items():
        lines.append(f"| {group.value} | {len(evidence)} |")
    if assessment.conflicts:
        lines.extend(["", "## Critical Conflicts"])
        lines.extend(f"- {item.topic}: {item.explanation}" for item in assessment.conflicts)
    if assessment.triggered_invalidations:
        lines.extend(["", "## Triggered Invalidations"])
        lines.extend(f"- {item.condition_id}: {item.rationale}" for item in assessment.triggered_invalidations)
    return "\n".join(lines)


def create_synthesis_manager(llm):
    async def synthesis_manager_node(state) -> dict:
        from backend.trading_agents.dataflows.config import get_config

        fallback = _deterministic_assessment(state)
        if not get_config().get("synthesis_enabled", True):
            return {
                "synthesis_report": "Synthesis disabled by user settings.",
                "synthesis_json": fallback.model_dump(mode="json"),
                "market_regime_json": fallback.market_regime.model_dump(mode="json") if fallback.market_regime else {},
            }

        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(ticker, asset_type)

        macd_results, rsi_results = await run_macd_rsi_backtests(ticker, state.get("trade_date"))

        from backend.trading_agents.agents.analyst_registry import get_report_fields
        from backend.trading_agents.agents.runtime.report_aggregator import build_resources

        summary_only = get_config().get("summary_only_mode", False)
        resources_text = build_resources(state, get_report_fields(), prefix="### ", summary_only=summary_only)
        invalidation_catalog = list(_plan_invalidation_catalog(state).values())

        default_instruction = (
            f"You are a Senior Investment Strategist. Synthesize analyst reports and historical backtests for {ticker}. "
            "Identify grounded alignments, conflicts, data gaps, independent evidence groups, and triggered invalidations."
        )
        instruction = get_system_instruction_override("synthesis_manager") or default_instruction

        prompt = f"""{instruction}

### Objective:
1. Identify grounded alignments and contradictions without inventing unavailable data.
2. Extract source-aware evidence items and explicitly mark review-origin evidence as non-independent.
3. Record only actually triggered invalidations from the exact catalog below. Never invent a condition_id or severity. Link supporting EvidenceItem.related_invalidation_ids to the condition. Open concerns belong in unresolved_questions.
4. Return a structured SynthesisAssessment, including a MarketRegimeSnapshot when macro evidence permits it.

### Allowed Invalidation Catalog:
{json.dumps(invalidation_catalog, ensure_ascii=False, default=str)}

### Historical Baseline (Backtests):
{macd_results}
{rsi_results}

### Analyst Resources:
{resources_text}

{instrument_context}

{get_general_settings_block()}"""
        try:
            result = await ainvoke_structured_or_freetext(
                bind_structured(llm, SynthesisAssessment, "Synthesis Manager"),
                llm,
                prompt,
                "Synthesis Manager",
                schema=SynthesisAssessment,
            )
            if isinstance(result, SynthesisAssessment):
                assessment = _sanitize_triggered_invalidations(state, result)
                report = _render_assessment(assessment)
            else:
                assessment = fallback
                report = str(result).strip() or _render_assessment(assessment)
        except Exception as exc:  # noqa: BLE001 - structured fallback keeps controller safe
            _logger.warning("Structured synthesis failed for %s: %s", ticker, exc)
            assessment = fallback
            report = _render_assessment(assessment)
        return {
            "synthesis_report": report,
            "synthesis_json": assessment.model_dump(mode="json"),
            "market_regime_json": assessment.market_regime.model_dump(mode="json") if assessment.market_regime else {},
        }

    return synthesis_manager_node