from backend.trading_agents.agents.schemas import (
    AnalystEvidenceAssessment,
    DataQualityAssessment,
    DataQualityLevel,
    EvidenceGroup,
    EvidenceItem,
    EvidenceSourceFamily,
    EvidenceStrength,
    InvalidationSeverity,
    ResearchBias,
    SynthesisAssessment,
    TriggeredInvalidation,
)
from backend.trading_agents.agents.sub.managers.synthesis_manager import _sanitize_triggered_invalidations


def _evidence(evidence_id: str, group: EvidenceGroup, condition_id: str) -> EvidenceItem:
    family = (
        EvidenceSourceFamily.MARKET_DATA
        if group is EvidenceGroup.TECHNICAL
        else EvidenceSourceFamily.CORPORATE_FUNDAMENTALS
    )
    return EvidenceItem(
        evidence_id=evidence_id,
        analyst=f"{group.value}-analyst",
        evidence_group=group,
        bias=ResearchBias.BEARISH,
        evidence_strength=EvidenceStrength.STRONG,
        claim="Evidence materially deteriorated.",
        source_family=family,
        related_invalidation_ids=[condition_id],
    )


def _assessment(condition_id: str, *, severity: InvalidationSeverity, two_groups: bool) -> SynthesisAssessment:
    technical = _evidence("technical_break", EvidenceGroup.TECHNICAL, condition_id)
    groups = {EvidenceGroup.TECHNICAL: [technical]}
    analysts = [
        AnalystEvidenceAssessment(
            analyst="technical-analyst",
            evidence_group=EvidenceGroup.TECHNICAL,
            bias=ResearchBias.BEARISH,
            evidence_strength=EvidenceStrength.STRONG,
            evidence_ids=[technical.evidence_id],
        )
    ]
    evidence_ids = [technical.evidence_id]
    if two_groups:
        fundamental = _evidence("guidance_cut", EvidenceGroup.FUNDAMENTAL, condition_id)
        groups[EvidenceGroup.FUNDAMENTAL] = [fundamental]
        analysts.append(
            AnalystEvidenceAssessment(
                analyst="fundamental-analyst",
                evidence_group=EvidenceGroup.FUNDAMENTAL,
                bias=ResearchBias.BEARISH,
                evidence_strength=EvidenceStrength.STRONG,
                evidence_ids=[fundamental.evidence_id],
            )
        )
        evidence_ids.append(fundamental.evidence_id)
    return SynthesisAssessment(
        dominant_bias=ResearchBias.BEARISH,
        analysts=analysts,
        evidence_groups=groups,
        triggered_invalidations=[
            TriggeredInvalidation(
                condition_id=condition_id,
                severity=severity,
                rationale="The planned condition fired.",
                evidence_ids=evidence_ids,
            )
        ],
        data_quality=DataQualityAssessment(
            level=DataQualityLevel.HIGH,
            score=90,
            available_evidence_groups=list(groups),
        ),
    )


def test_unknown_invalidation_id_is_dropped() -> None:
    assessment = _assessment("invented_condition", severity=InvalidationSeverity.CRITICAL, two_groups=True)
    state = {
        "analysis_plan_json": {
            "invalidations_to_check": [
                {"condition_id": "known_condition", "severity": "critical"}
            ]
        }
    }

    sanitized = _sanitize_triggered_invalidations(state, assessment)

    assert sanitized.triggered_invalidations == []


def test_plan_is_authoritative_for_invalidation_severity() -> None:
    assessment = _assessment("margin_break", severity=InvalidationSeverity.WATCH, two_groups=False)
    state = {
        "analysis_plan_json": {
            "invalidations_to_check": [
                {"condition_id": "margin_break", "severity": "material"}
            ]
        }
    }

    sanitized = _sanitize_triggered_invalidations(state, assessment)

    assert len(sanitized.triggered_invalidations) == 1
    assert sanitized.triggered_invalidations[0].severity is InvalidationSeverity.MATERIAL


def test_critical_invalidation_needs_two_independent_evidence_groups() -> None:
    assessment = _assessment("core_break", severity=InvalidationSeverity.CRITICAL, two_groups=False)
    state = {
        "analysis_plan_json": {
            "invalidations_to_check": [
                {"condition_id": "core_break", "severity": "critical"}
            ]
        }
    }

    sanitized = _sanitize_triggered_invalidations(state, assessment)

    assert sanitized.triggered_invalidations == []
