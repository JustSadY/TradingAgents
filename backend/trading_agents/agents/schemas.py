from __future__ import annotations

import math
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.trading_agents.agents.utils.report_localization import report_bias, report_rating, report_texts


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"

    @property
    def score(self) -> int:
        """Ordinal rating used exclusively for deterministic transition checks.

        The score is deliberately not a position size or an execution instruction.
        It lets a stability controller distinguish a one-step adjustment from a
        cross-zero reversal without asking an LLM to interpret rating labels.
        """

        return {
            PortfolioRating.SELL: -2,
            PortfolioRating.UNDERWEIGHT: -1,
            PortfolioRating.HOLD: 0,
            PortfolioRating.OVERWEIGHT: 1,
            PortfolioRating.BUY: 2,
        }[self]

class ResearchBias(str, Enum):
    """Non-executable research posture used by upstream research agents.

    This deliberately does not reuse :class:`PortfolioRating`.  Research and
    risk agents are evidence producers, while the Portfolio Manager is the
    only component allowed to produce a Buy/Sell/Hold-style decision.
    """

    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"


class StructuredAgentSchema(BaseModel):
    """Strict, JSON-safe base model for new graph/service contracts.

    Existing LLM-facing models intentionally retain Pydantic's permissive legacy
    behaviour.  New state that controls plan revisions or decision acceptance is
    instead explicit about unknown fields and validates assignments, so a stale
    graph node cannot silently alter a decision contract.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    def as_json_dict(self) -> dict[str, Any]:
        """Return a JSON-column / graph-state safe representation."""

        return self.model_dump(mode="json")


class AnalysisPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class EvidenceGroup(str, Enum):
    """Independent evidence domains, not individual agent names."""

    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    MACRO_SENTIMENT = "macro_sentiment"
    CATALYST_OPTIONS = "catalyst_options"
    REVIEW = "review"
    OTHER = "other"


class EvidenceSourceFamily(str, Enum):
    """Origin family used to avoid double-counting correlated evidence."""

    MARKET_DATA = "market_data"
    CORPORATE_FUNDAMENTALS = "corporate_fundamentals"
    MACROECONOMIC = "macroeconomic"
    NEWS = "news"
    DERIVATIVES = "derivatives"
    INSTITUTIONAL = "institutional"
    MODEL_DERIVED = "model_derived"
    INTERNAL_REVIEW = "internal_review"
    OTHER = "other"


class EvidenceStrength(str, Enum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class EvidenceCoverage(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DataQualityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InvalidationKind(str, Enum):
    """Whether an invalidation can be measured, observed as an event, or judged."""

    METRIC = "metric"
    EVENT = "event"
    QUALITATIVE = "qualitative"


class ComparisonOperator(str, Enum):
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    EQUAL = "eq"
    NOT_EQUAL = "neq"


class InvalidationSeverity(str, Enum):
    WATCH = "watch"
    MATERIAL = "material"
    CRITICAL = "critical"


class InvalidationStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    NOT_TRIGGERED = "not_triggered"
    TRIGGERED = "triggered"


class MarketTrend(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE_BOUND = "range_bound"
    UNCERTAIN = "uncertain"


class VolatilityRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


class RiskRegime(str, Enum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


class MacroRegime(str, Enum):
    EARLY_EXPANSION = "early_expansion"
    MID_EXPANSION = "mid_expansion"
    LATE_EXPANSION = "late_expansion"
    CONTRACTION = "contraction"
    STAGFLATION = "stagflation"
    DISINFLATION = "disinflation"
    UNCERTAIN = "uncertain"


class AssetStrategyStatus(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class StrategyRevisionAction(str, Enum):
    CREATE = "CREATE"
    KEEP = "KEEP"
    STRENGTHEN = "STRENGTHEN"
    WEAKEN = "WEAKEN"
    INVALIDATE = "INVALIDATE"
    REBUILD = "REBUILD"


class StrategyChangeStrength(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MATERIAL = "material"
    MAJOR = "major"


class StrategicState(str, Enum):
    BULLISH = "BULLISH"
    BULLISH_WEAKENING = "BULLISH_WEAKENING"
    NEUTRAL = "NEUTRAL"
    BEARISH_WEAKENING = "BEARISH_WEAKENING"
    BEARISH = "BEARISH"
    INVALIDATED = "INVALIDATED"


class TacticalAction(str, Enum):
    INCREASE_EXPOSURE = "INCREASE_EXPOSURE"
    HOLD = "HOLD"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    EXIT = "EXIT"
    COVER_SHORT = "COVER_SHORT"


class ExecutionAction(str, Enum):
    PLACE_ORDER = "PLACE_ORDER"
    NO_NEW_ORDER = "NO_NEW_ORDER"
    REDUCE_ONLY = "REDUCE_ONLY"
    FREEZE = "FREEZE"


class DecisionTransitionOutcome(str, Enum):
    INITIAL_ACCEPTED = "INITIAL_ACCEPTED"
    UNCHANGED = "UNCHANGED"
    ACCEPTED_CHANGE = "ACCEPTED_CHANGE"
    BLOCKED_CHANGE = "BLOCKED_CHANGE"
    EMERGENCY_RISK_EXIT = "EMERGENCY_RISK_EXIT"


class ReversalVerdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


_DIRECTIONAL_PLAN_TERMS = re.compile(
    r"\b(?:buy|sell|overweight|underweight|position\s+size|entry\s+price|stop\s+loss)\b",
    re.IGNORECASE,
)


def _validate_neutral_investigation_text(value: str, field_name: str) -> str:
    """Prevent the planner from leaking a prior executable rating to analysts."""

    if _DIRECTIONAL_PLAN_TERMS.search(value):
        raise ValueError(
            f"{field_name} must be an evidence-seeking question or assumption, not an executable rating or order instruction"
        )
    return value


def _ensure_unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class PriorAssumption(StructuredAgentSchema):
    assumption_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1)
    test_method: str = Field(min_length=1)
    priority: AnalysisPriority = AnalysisPriority.NORMAL

    @field_validator("statement", "test_method")
    @classmethod
    def _neutral_text(cls, value: str, info) -> str:
        return _validate_neutral_investigation_text(value, info.field_name)


class PriorityEvidence(StructuredAgentSchema):
    description: str = Field(min_length=1)
    source_family: EvidenceSourceFamily
    priority: AnalysisPriority = AnalysisPriority.NORMAL

    @field_validator("description")
    @classmethod
    def _neutral_text(cls, value: str, info) -> str:
        return _validate_neutral_investigation_text(value, info.field_name)


class ThresholdMeasurement(StructuredAgentSchema):
    """A machine-evaluable threshold for a metric-based invalidation."""

    metric: str = Field(min_length=1, max_length=160)
    operator: ComparisonOperator
    threshold: float
    unit: str = Field(min_length=1, max_length=64)
    observation_window: str | None = Field(
        default=None,
        description="Evaluation period, e.g. 'two consecutive fiscal quarters'.",
    )


class InvalidationCondition(StructuredAgentSchema):
    """An exact thesis failure condition, with measurable form whenever possible."""

    condition_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1)
    kind: InvalidationKind
    severity: InvalidationSeverity = InvalidationSeverity.MATERIAL
    measurement: ThresholdMeasurement | None = None
    event_name: str | None = Field(default=None, min_length=1)
    qualitative_criteria: str | None = Field(default=None, min_length=1)
    status: InvalidationStatus = InvalidationStatus.NOT_EVALUATED

    @model_validator(mode="after")
    def _validate_shape(self) -> InvalidationCondition:
        if self.kind is InvalidationKind.METRIC:
            if self.measurement is None:
                raise ValueError("metric invalidation conditions require a measurement")
            if self.event_name is not None or self.qualitative_criteria is not None:
                raise ValueError("metric invalidation conditions cannot include event_name or qualitative_criteria")
        elif self.kind is InvalidationKind.EVENT:
            if not self.event_name:
                raise ValueError("event invalidation conditions require event_name")
            if self.measurement is not None or self.qualitative_criteria is not None:
                raise ValueError("event invalidation conditions cannot include measurement or qualitative_criteria")
        elif self.kind is InvalidationKind.QUALITATIVE:
            if not self.qualitative_criteria:
                raise ValueError("qualitative invalidation conditions require qualitative_criteria")
            if self.measurement is not None or self.event_name is not None:
                raise ValueError("qualitative invalidation conditions cannot include measurement or event_name")
        return self


class TriggeredInvalidation(StructuredAgentSchema):
    """Evidence-backed record that one strategy condition actually fired."""

    condition_id: str = Field(min_length=1, max_length=128)
    severity: InvalidationSeverity
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    triggered_at: datetime | None = None

    @field_validator("evidence_ids")
    @classmethod
    def _unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "evidence_ids")


class AnalysisPlan(StructuredAgentSchema):
    """A direction-neutral investigation plan created before fresh research.

    It intentionally has no rating, sizing, entry, or order fields.  The
    analyst-question map permits both team names (``technical``) and specific
    analyst names while preserving an LLM-friendly JSON object shape.
    """

    objective: str = Field(min_length=1)
    prior_assumptions_to_test: list[PriorAssumption] = Field(default_factory=list)
    invalidations_to_check: list[InvalidationCondition] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    analyst_questions: dict[str, list[str]] = Field(min_length=1)
    priority_evidence: list[PriorityEvidence] = Field(default_factory=list)
    expected_data_gaps: list[str] = Field(default_factory=list)
    horizon: str = Field(min_length=1)
    source_strategy_version: int | None = Field(default=None, ge=1)

    @field_validator("objective", "horizon")
    @classmethod
    def _neutral_top_level_text(cls, value: str, info) -> str:
        return _validate_neutral_investigation_text(value, info.field_name)

    @field_validator("unresolved_questions", "expected_data_gaps")
    @classmethod
    def _clean_text_lists(cls, value: list[str], info) -> list[str]:
        _ensure_unique(value, info.field_name)
        for item in value:
            _validate_neutral_investigation_text(item, info.field_name)
        return value

    @field_validator("prior_assumptions_to_test")
    @classmethod
    def _unique_assumptions(cls, value: list[PriorAssumption]) -> list[PriorAssumption]:
        _ensure_unique([item.assumption_id for item in value], "prior_assumptions_to_test.assumption_id")
        return value

    @field_validator("invalidations_to_check")
    @classmethod
    def _unique_invalidations(cls, value: list[InvalidationCondition]) -> list[InvalidationCondition]:
        _ensure_unique([item.condition_id for item in value], "invalidations_to_check.condition_id")
        for condition in value:
            _validate_neutral_investigation_text(condition.statement, "invalidations_to_check.statement")
            if condition.event_name:
                _validate_neutral_investigation_text(condition.event_name, "invalidations_to_check.event_name")
            if condition.qualitative_criteria:
                _validate_neutral_investigation_text(
                    condition.qualitative_criteria,
                    "invalidations_to_check.qualitative_criteria",
                )
        return value

    @field_validator("analyst_questions")
    @classmethod
    def _validate_analyst_questions(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for analyst_or_team, questions in value.items():
            if not analyst_or_team:
                raise ValueError("analyst_questions cannot contain an empty analyst/team key")
            if not questions:
                raise ValueError(f"analyst_questions[{analyst_or_team!r}] must contain at least one question")
            _ensure_unique(questions, f"analyst_questions[{analyst_or_team!r}]")
            for question in questions:
                _validate_neutral_investigation_text(question, f"analyst_questions[{analyst_or_team!r}]")
        return value


class EvidenceItem(StructuredAgentSchema):
    """A source-aware atomic claim consumed by synthesis and reversal checks."""

    evidence_id: str = Field(min_length=1, max_length=128)
    analyst: str = Field(min_length=1, max_length=128)
    evidence_group: EvidenceGroup
    bias: ResearchBias
    evidence_strength: EvidenceStrength
    claim: str = Field(min_length=1)
    source_family: EvidenceSourceFamily
    source_reference: str | None = Field(default=None, min_length=1)
    observed_at: datetime | None = None
    independent_for_reversal: bool = True
    related_assumption_ids: list[str] = Field(default_factory=list)
    related_invalidation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _review_is_not_independent(self) -> EvidenceItem:
        if (
            self.evidence_group is EvidenceGroup.REVIEW
            or self.source_family is EvidenceSourceFamily.INTERNAL_REVIEW
        ) and self.independent_for_reversal:
            raise ValueError("review-origin evidence cannot count as independent reversal confirmation")
        return self

    @field_validator("related_assumption_ids", "related_invalidation_ids")
    @classmethod
    def _unique_relationship_ids(cls, value: list[str], info) -> list[str]:
        return _ensure_unique(value, info.field_name)


class AnalystEvidenceAssessment(StructuredAgentSchema):
    analyst: str = Field(min_length=1, max_length=128)
    evidence_group: EvidenceGroup
    bias: ResearchBias
    evidence_strength: EvidenceStrength
    coverage: EvidenceCoverage = EvidenceCoverage.AVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unavailable_has_no_evidence(self) -> AnalystEvidenceAssessment:
        if self.coverage is EvidenceCoverage.UNAVAILABLE and self.evidence_ids:
            raise ValueError("unavailable analysts cannot cite evidence_ids")
        return self

    @field_validator("evidence_ids")
    @classmethod
    def _unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "evidence_ids")


class EvidenceAlignment(StructuredAgentSchema):
    topic: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=2)
    evidence_groups: list[EvidenceGroup] = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def _unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "alignment.evidence_ids")

    @field_validator("evidence_groups")
    @classmethod
    def _unique_evidence_groups(cls, value: list[EvidenceGroup]) -> list[EvidenceGroup]:
        if len(value) != len(set(value)):
            raise ValueError("alignment.evidence_groups must not contain duplicates")
        return value


class EvidenceConflict(StructuredAgentSchema):
    topic: str = Field(min_length=1)
    supporting_evidence_ids: list[str] = Field(min_length=1)
    contradicting_evidence_ids: list[str] = Field(min_length=1)
    evidence_groups: list[EvidenceGroup] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    resolved: bool = False

    @model_validator(mode="after")
    def _conflict_has_distinct_evidence(self) -> EvidenceConflict:
        support = set(self.supporting_evidence_ids)
        contradiction = set(self.contradicting_evidence_ids)
        if support & contradiction:
            raise ValueError("conflict evidence cannot simultaneously support and contradict the same topic")
        return self

    @field_validator("supporting_evidence_ids", "contradicting_evidence_ids")
    @classmethod
    def _unique_evidence_ids(cls, value: list[str], info) -> list[str]:
        return _ensure_unique(value, info.field_name)

    @field_validator("evidence_groups")
    @classmethod
    def _unique_evidence_groups(cls, value: list[EvidenceGroup]) -> list[EvidenceGroup]:
        if len(value) != len(set(value)):
            raise ValueError("conflict.evidence_groups must not contain duplicates")
        return value


class DataQualityAssessment(StructuredAgentSchema):
    level: DataQualityLevel
    score: float = Field(ge=0.0, le=100.0)
    available_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    unavailable_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coverage_sets_do_not_overlap(self) -> DataQualityAssessment:
        available = set(self.available_evidence_groups)
        unavailable = set(self.unavailable_evidence_groups)
        if available & unavailable:
            raise ValueError("available_evidence_groups and unavailable_evidence_groups cannot overlap")
        return self

    @field_validator("available_evidence_groups", "unavailable_evidence_groups")
    @classmethod
    def _unique_evidence_groups(cls, value: list[EvidenceGroup], info) -> list[EvidenceGroup]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        return value

    @field_validator("known_gaps")
    @classmethod
    def _unique_gaps(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "known_gaps")


class MarketRegimeSnapshot(StructuredAgentSchema):
    trend: MarketTrend
    volatility: VolatilityRegime
    risk: RiskRegime
    macro: MacroRegime
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: datetime | None = None


class SynthesisAssessment(StructuredAgentSchema):
    """Machine-readable companion to the current human-facing synthesis report."""

    dominant_bias: ResearchBias
    analysts: list[AnalystEvidenceAssessment] = Field(min_length=1)
    evidence_groups: dict[EvidenceGroup, list[EvidenceItem]] = Field(min_length=1)
    alignments: list[EvidenceAlignment] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    triggered_invalidations: list[TriggeredInvalidation] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    data_quality: DataQualityAssessment
    market_regime: MarketRegimeSnapshot | None = None

    @model_validator(mode="after")
    def _validate_evidence_references(self) -> SynthesisAssessment:
        evidence_by_id: dict[str, EvidenceItem] = {}
        for group, evidence_items in self.evidence_groups.items():
            for item in evidence_items:
                if item.evidence_group is not group:
                    raise ValueError(
                        f"evidence {item.evidence_id!r} belongs to {item.evidence_group.value!r}, "
                        f"not evidence_groups[{group.value!r}]"
                    )
                if item.evidence_id in evidence_by_id:
                    raise ValueError(f"evidence_id {item.evidence_id!r} appears more than once")
                evidence_by_id[item.evidence_id] = item

        known_ids = set(evidence_by_id)
        analyst_keys: set[tuple[str, EvidenceGroup]] = set()
        for analyst in self.analysts:
            analyst_key = (analyst.analyst, analyst.evidence_group)
            if analyst_key in analyst_keys:
                raise ValueError(f"duplicate analyst assessment for {analyst.analyst!r} / {analyst.evidence_group.value}")
            analyst_keys.add(analyst_key)
            unknown = set(analyst.evidence_ids) - known_ids
            if unknown:
                raise ValueError(f"analyst {analyst.analyst!r} references unknown evidence_ids: {sorted(unknown)}")

        def ensure_known(ids: list[str], label: str) -> None:
            unknown = set(ids) - known_ids
            if unknown:
                raise ValueError(f"{label} references unknown evidence_ids: {sorted(unknown)}")

        for alignment in self.alignments:
            ensure_known(alignment.evidence_ids, f"alignment {alignment.topic!r}")
        for conflict in self.conflicts:
            ensure_known(conflict.supporting_evidence_ids, f"conflict {conflict.topic!r} supporting evidence")
            ensure_known(conflict.contradicting_evidence_ids, f"conflict {conflict.topic!r} contradicting evidence")
        for invalidation in self.triggered_invalidations:
            ensure_known(invalidation.evidence_ids, f"triggered invalidation {invalidation.condition_id!r}")

        _ensure_unique(self.unresolved_questions, "unresolved_questions")
        _ensure_unique(
            [item.condition_id for item in self.triggered_invalidations],
            "triggered_invalidations.condition_id",
        )
        return self


class AssetStrategySnapshot(StructuredAgentSchema):
    """Exact, persistent state of the current belief for one asset.

    This is intentionally distinct from vector/episodic memory.  It represents
    the current thesis that a later run must revalidate, and includes an
    ``effective_at`` point for historical replay safety.
    """

    strategy_id: int | None = Field(default=None, ge=1)
    user_id: int | None = Field(default=None, ge=1)
    ticker: str = Field(min_length=1, max_length=50)
    asset_type: str = Field(default="stock", min_length=1, max_length=20)
    status: AssetStrategyStatus = AssetStrategyStatus.ACTIVE
    version: int = Field(ge=1)
    strategic_bias: ResearchBias
    conviction: float = Field(ge=0.0, le=1.0)
    accepted_rating: PortfolioRating | None = None
    thesis: str = Field(min_length=1)
    key_drivers: list[str] = Field(default_factory=list)
    watch_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[InvalidationCondition] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    regime_assumption: MarketRegimeSnapshot | None = None
    time_horizon: str | None = Field(default=None, min_length=1)
    last_analysis_id: int | None = Field(default=None, ge=1)
    effective_at: datetime | None = None
    recorded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_reviewed_at: datetime | None = None

    @field_validator("ticker")
    @classmethod
    def _normalise_ticker(cls, value: str) -> str:
        return value.upper()

    @field_validator("asset_type")
    @classmethod
    def _normalise_asset_type(cls, value: str) -> str:
        return value.lower()

    @field_validator("strategic_bias", mode="before")
    @classmethod
    def _accept_storage_bias(cls, value: object) -> object:
        """Accept uppercase database snapshots as well as agent-facing labels."""

        if isinstance(value, str):
            return {
                "BULLISH": ResearchBias.BULLISH.value,
                "NEUTRAL": ResearchBias.NEUTRAL.value,
                "BEARISH": ResearchBias.BEARISH.value,
            }.get(value.strip().upper(), value)
        return value

    @field_validator("accepted_rating", mode="before")
    @classmethod
    def _accept_storage_rating(cls, value: object) -> object:
        """Accept uppercase database snapshots without changing public ratings."""

        if isinstance(value, str):
            return {
                "BUY": PortfolioRating.BUY.value,
                "OVERWEIGHT": PortfolioRating.OVERWEIGHT.value,
                "HOLD": PortfolioRating.HOLD.value,
                "UNDERWEIGHT": PortfolioRating.UNDERWEIGHT.value,
                "SELL": PortfolioRating.SELL.value,
            }.get(value.strip().upper(), value)
        return value

    @field_validator("regime_assumption", mode="before")
    @classmethod
    def _empty_regime_is_absent(cls, value: object) -> object:
        # The persistence layer uses an empty JSON object as its database
        # default.  Treat it as missing context, rather than rejecting an
        # otherwise valid legacy/provisional strategy snapshot.
        return None if value == {} else value

    @field_validator("key_drivers", "watch_conditions", "open_questions")
    @classmethod
    def _unique_text_lists(cls, value: list[str], info) -> list[str]:
        return _ensure_unique(value, info.field_name)

    @field_validator("invalidation_conditions")
    @classmethod
    def _unique_invalidation_ids(cls, value: list[InvalidationCondition]) -> list[InvalidationCondition]:
        _ensure_unique([condition.condition_id for condition in value], "invalidation_conditions.condition_id")
        return value


class StrategyRevisionCandidate(StructuredAgentSchema):
    """A non-persisted proposed strategy transition, guarded by CAS versioning."""

    revision_action: StrategyRevisionAction
    expected_version: int | None = Field(default=None, ge=1)
    strategy_before: AssetStrategySnapshot | None = None
    strategy_after: AssetStrategySnapshot | None = None
    change_strength: StrategyChangeStrength
    revision_reason: str = Field(min_length=1)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    triggered_invalidations: list[TriggeredInvalidation] = Field(default_factory=list)
    regime_before: MarketRegimeSnapshot | None = None
    regime_after: MarketRegimeSnapshot | None = None
    analysis_id: int | None = Field(default=None, ge=1)

    @staticmethod
    def _assert_same_lineage(before: AssetStrategySnapshot, after: AssetStrategySnapshot) -> None:
        if before.ticker != after.ticker or before.asset_type != after.asset_type:
            raise ValueError("strategy revisions must preserve ticker and asset_type")
        if before.strategy_id is not None and after.strategy_id is not None and before.strategy_id != after.strategy_id:
            raise ValueError("strategy revisions must preserve strategy_id unless revision_action is REBUILD")

    @model_validator(mode="after")
    def _validate_transition(self) -> StrategyRevisionCandidate:
        before = self.strategy_before
        after = self.strategy_after

        if before is not None and self.expected_version != before.version:
            raise ValueError("expected_version must match strategy_before.version for optimistic locking")

        if self.revision_action is StrategyRevisionAction.CREATE:
            if before is not None or self.expected_version is not None or after is None:
                raise ValueError("CREATE requires no prior strategy, no expected_version, and a strategy_after")
            if after.version != 1 or after.status not in {AssetStrategyStatus.PROVISIONAL, AssetStrategyStatus.ACTIVE}:
                raise ValueError("CREATE must create a version 1 PROVISIONAL or ACTIVE strategy")

        elif self.revision_action is StrategyRevisionAction.KEEP:
            if before is None or after is None:
                raise ValueError("KEEP requires strategy_before and strategy_after")
            self._assert_same_lineage(before, after)
            if after.version != before.version:
                raise ValueError("KEEP must retain the existing strategy version")
            if after.strategic_bias is not before.strategic_bias or after.accepted_rating is not before.accepted_rating:
                raise ValueError("KEEP cannot change strategic_bias or accepted_rating")
            if self.change_strength not in {StrategyChangeStrength.NONE, StrategyChangeStrength.MINOR}:
                raise ValueError("KEEP must have none or minor change_strength")

        elif self.revision_action in {StrategyRevisionAction.STRENGTHEN, StrategyRevisionAction.WEAKEN}:
            if before is None or after is None:
                raise ValueError(f"{self.revision_action.value} requires strategy_before and strategy_after")
            self._assert_same_lineage(before, after)
            if after.version != before.version + 1:
                raise ValueError(f"{self.revision_action.value} must increment strategy version by one")
            if self.change_strength not in {StrategyChangeStrength.MATERIAL, StrategyChangeStrength.MAJOR}:
                raise ValueError(f"{self.revision_action.value} requires a material or major change_strength")
            if self.revision_action is StrategyRevisionAction.STRENGTHEN and after.conviction <= before.conviction:
                raise ValueError("STRENGTHEN must increase conviction")
            if self.revision_action is StrategyRevisionAction.WEAKEN and after.conviction >= before.conviction:
                raise ValueError("WEAKEN must decrease conviction")

        elif self.revision_action is StrategyRevisionAction.INVALIDATE:
            if before is None:
                raise ValueError("INVALIDATE requires strategy_before")
            if not self.triggered_invalidations:
                raise ValueError("INVALIDATE requires at least one triggered invalidation")
            if self.change_strength is not StrategyChangeStrength.MAJOR:
                raise ValueError("INVALIDATE requires major change_strength")
            if after is not None:
                self._assert_same_lineage(before, after)
                if after.version != before.version + 1:
                    raise ValueError("INVALIDATE must increment strategy version by one when strategy_after is supplied")
                if after.status not in {AssetStrategyStatus.INVALIDATED, AssetStrategyStatus.CLOSED}:
                    raise ValueError("INVALIDATE strategy_after must be INVALIDATED or CLOSED")

        elif self.revision_action is StrategyRevisionAction.REBUILD:
            if before is None or after is None:
                raise ValueError("REBUILD requires strategy_before and a replacement strategy_after")
            if before.status not in {AssetStrategyStatus.INVALIDATED, AssetStrategyStatus.CLOSED}:
                raise ValueError(
                    "REBUILD requires an INVALIDATED or CLOSED predecessor; "
                    "an ACTIVE thesis must first be explicitly invalidated"
                )
            if before.ticker != after.ticker or before.asset_type != after.asset_type:
                raise ValueError("REBUILD must preserve ticker and asset_type")
            if before.strategy_id is not None and after.strategy_id is not None and before.strategy_id == after.strategy_id:
                raise ValueError("REBUILD requires a new strategy lineage")
            if after.version != 1:
                raise ValueError("REBUILD replacement strategy must begin at version 1")
            if after.status not in {AssetStrategyStatus.PROVISIONAL, AssetStrategyStatus.ACTIVE}:
                raise ValueError("REBUILD replacement strategy must be PROVISIONAL or ACTIVE")
            if self.change_strength is not StrategyChangeStrength.MAJOR:
                raise ValueError("REBUILD requires major change_strength")

        _ensure_unique([item.evidence_id for item in self.supporting_evidence], "supporting_evidence.evidence_id")
        _ensure_unique(
            [item.condition_id for item in self.triggered_invalidations],
            "triggered_invalidations.condition_id",
        )
        return self


class PMDecisionProposal(StructuredAgentSchema):
    """Raw Portfolio Manager output.  It is not executable until accepted."""

    proposed_decision: PortfolioDecision
    rationale: str = Field(min_length=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    triggered_invalidation_ids: list[str] = Field(default_factory=list)

    @field_validator("supporting_evidence_ids", "triggered_invalidation_ids")
    @classmethod
    def _unique_ids(cls, value: list[str], info) -> list[str]:
        return _ensure_unique(value, info.field_name)


class AcceptedDecision(StructuredAgentSchema):
    """Controller-approved canonical decision and its safe tactical outcome."""

    decision: PortfolioDecision
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    strategic_state: StrategicState
    tactical_action: TacticalAction
    execution_action: ExecutionAction

    @model_validator(mode="after")
    def _validate_action_contract(self) -> AcceptedDecision:
        if not math.isclose(self.decision.confidence_score, self.calibrated_confidence, abs_tol=1e-9):
            raise ValueError("accepted decision confidence_score must equal calibrated_confidence")

        rating = self.decision.rating
        if self.tactical_action is TacticalAction.HOLD and rating is not PortfolioRating.HOLD:
            raise ValueError("HOLD tactical action requires a Hold accepted rating")
        if self.tactical_action is TacticalAction.INCREASE_EXPOSURE and rating not in {
            PortfolioRating.BUY,
            PortfolioRating.OVERWEIGHT,
        }:
            raise ValueError("INCREASE_EXPOSURE requires Buy or Overweight accepted rating")
        if self.tactical_action is TacticalAction.REDUCE_EXPOSURE and rating not in {
            PortfolioRating.UNDERWEIGHT,
            PortfolioRating.SELL,
        }:
            raise ValueError("REDUCE_EXPOSURE requires Underweight or Sell accepted rating")
        if self.tactical_action is TacticalAction.EXIT and rating is not PortfolioRating.SELL:
            raise ValueError("EXIT requires Sell accepted rating")
        if self.tactical_action is TacticalAction.COVER_SHORT and rating not in {
            PortfolioRating.BUY,
            PortfolioRating.OVERWEIGHT,
        }:
            raise ValueError("COVER_SHORT requires Buy or Overweight accepted rating")
        if self.execution_action in {ExecutionAction.NO_NEW_ORDER, ExecutionAction.FREEZE} and self.tactical_action is not TacticalAction.HOLD:
            raise ValueError("NO_NEW_ORDER and FREEZE are only valid with a HOLD tactical action")
        if self.execution_action is ExecutionAction.REDUCE_ONLY and self.tactical_action not in {
            TacticalAction.REDUCE_EXPOSURE,
            TacticalAction.EXIT,
            TacticalAction.COVER_SHORT,
        }:
            raise ValueError("REDUCE_ONLY requires a risk-reducing tactical action")
        if self.execution_action is ExecutionAction.PLACE_ORDER and self.tactical_action is TacticalAction.HOLD:
            raise ValueError("PLACE_ORDER cannot be used with a HOLD tactical action")
        return self


class ReversalVerification(StructuredAgentSchema):
    verdict: ReversalVerdict
    rationale: str = Field(min_length=1)
    independent_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    invalidation_condition_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approve_requires_independence(self) -> ReversalVerification:
        if self.verdict is ReversalVerdict.APPROVE and len(self.independent_evidence_groups) < 2:
            raise ValueError("an approved major reversal requires at least two independent evidence groups")
        return self

    @field_validator("independent_evidence_groups")
    @classmethod
    def _unique_groups(cls, value: list[EvidenceGroup]) -> list[EvidenceGroup]:
        if EvidenceGroup.REVIEW in value:
            raise ValueError("review is not an independent evidence group for reversal confirmation")
        if len(value) != len(set(value)):
            raise ValueError("independent_evidence_groups must not contain duplicates")
        return value

    @field_validator("invalidation_condition_ids")
    @classmethod
    def _unique_condition_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "invalidation_condition_ids")


class DecisionTransition(StructuredAgentSchema):
    """Auditable distinction between a PM proposal and the accepted decision."""

    previous_accepted_decision: PortfolioDecision | None = None
    pm_proposal: PMDecisionProposal
    accepted_decision: AcceptedDecision
    outcome: DecisionTransitionOutcome
    reason: str = Field(min_length=1)
    evidence_strength: EvidenceStrength
    run_quality: DataQualityAssessment
    reversal_verification: ReversalVerification | None = None

    @property
    def previous_rating(self) -> PortfolioRating | None:
        return self.previous_accepted_decision.rating if self.previous_accepted_decision else None

    @property
    def proposed_rating(self) -> PortfolioRating:
        return self.pm_proposal.proposed_decision.rating

    @property
    def accepted_rating(self) -> PortfolioRating:
        return self.accepted_decision.decision.rating

    @property
    def proposed_rating_delta(self) -> int:
        """Signed change from the prior rating to the raw PM proposal."""

        if self.previous_rating is None:
            return 0
        return self.proposed_rating.score - self.previous_rating.score

    @property
    def accepted_rating_delta(self) -> int:
        """Signed change from the prior rating to the controller output."""

        if self.previous_rating is None:
            return 0
        return self.accepted_rating.score - self.previous_rating.score

    @model_validator(mode="after")
    def _validate_outcome(self) -> DecisionTransition:
        if self.outcome is DecisionTransitionOutcome.INITIAL_ACCEPTED:
            if self.previous_accepted_decision is not None:
                raise ValueError("INITIAL_ACCEPTED cannot have a previous_accepted_decision")
        elif self.outcome is not DecisionTransitionOutcome.BLOCKED_CHANGE and self.previous_accepted_decision is None:
            raise ValueError(f"{self.outcome.value} requires a previous_accepted_decision")

        if self.outcome is DecisionTransitionOutcome.BLOCKED_CHANGE:
            if self.accepted_decision.tactical_action is not TacticalAction.HOLD:
                raise ValueError("BLOCKED_CHANGE must result in a HOLD tactical action")
            if self.accepted_decision.execution_action not in {
                ExecutionAction.NO_NEW_ORDER,
                ExecutionAction.FREEZE,
            }:
                raise ValueError("BLOCKED_CHANGE must not emit a new order")
            if self.proposed_rating is self.accepted_rating:
                raise ValueError("BLOCKED_CHANGE requires the accepted rating to differ from the raw PM proposal")

        if self.outcome is DecisionTransitionOutcome.EMERGENCY_RISK_EXIT:
            if self.accepted_decision.execution_action is not ExecutionAction.REDUCE_ONLY:
                raise ValueError("EMERGENCY_RISK_EXIT must use REDUCE_ONLY execution")
            if self.accepted_decision.tactical_action not in {
                TacticalAction.REDUCE_EXPOSURE,
                TacticalAction.EXIT,
                TacticalAction.COVER_SHORT,
            }:
                raise ValueError("EMERGENCY_RISK_EXIT must reduce or exit exposure")

        if (
            self.reversal_verification is not None
            and self.reversal_verification.verdict is not ReversalVerdict.APPROVE
            and self.outcome is DecisionTransitionOutcome.ACCEPTED_CHANGE
            and self.previous_accepted_decision is not None
            and abs(self.proposed_rating_delta) >= 3
        ):
            raise ValueError("a major accepted reversal requires an approved reversal verification")
        return self

class ResearchPlan(BaseModel):
    research_bias: ResearchBias = Field(
        description=(
            "The evidence posture only. Exactly one of Bullish / Neutral / Bearish. "
            "This is not a trading instruction; do not use Buy, Sell, Hold, "
            "Overweight, Underweight, quantities, or position sizes."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments support the evidence posture. "
            "Speak naturally, as if to a teammate."
        ),
    )
    key_evidence: str = Field(
        description=(
            "The most decision-relevant, source-grounded evidence, including "
            "what would invalidate it. Do not prescribe an order direction or size."
        ),
    )
    risk_conditions: str = Field(
        description=(
            "Open questions, invalidation conditions, and risk checks for the "
            "Portfolio Manager. Do not prescribe an order direction, entry, stop, "
            "target, leverage, or quantity."
        ),
    )

def render_research_plan(plan: ResearchPlan, output_language: str | None = None) -> str:
    labels = report_texts(("research_bias", "rationale", "key_evidence", "risk_conditions"), output_language)
    return "\n".join(
        [
            f"**{labels['research_bias']}**: {report_bias(plan.research_bias.value, output_language)}",
            "",
            f"**{labels['rationale']}**: {plan.rationale}",
            "",
            f"**{labels['key_evidence']}**: {plan.key_evidence}",
            "",
            f"**{labels['risk_conditions']}**: {plan.risk_conditions}",
        ]
    )

class PortfolioDecision(BaseModel):
    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "The Portfolio Manager's calibrated probability of a favourable outcome, "
            "from 0.0 to 1.0. This is the sole execution confidence used by the order "
            "engine; do not copy an upstream agent's score without reassessing it."
        ),
    )
    entry_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Planned entry or execution reference price in the instrument's quote currency. "
            "Required for a new Buy/Overweight entry when a reliable price is available; null for Hold."
        ),
    )
    stop_loss: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Protective stop price in the instrument's quote currency. For a long it must be below entry; "
            "for a short it must be above entry. Null only when no order should be opened."
        ),
    )
    take_profit_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Planned take-profit price in the instrument's quote currency. For a long it must be above entry; "
            "for a short it must be below entry. Null only when no order should be opened."
        ),
    )
    position_size_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Desired total allocation after the action as a percentage of current portfolio equity. "
            "REQUIRED and non-null for Buy, Overweight, and Underweight: the execution engine sizes "
            "the order from this number alone and skips the order entirely when it is null, so "
            "omitting it silently cancels the trade you just recommended. "
            "Use the full intended target weight for Buy/Overweight, a target below the current "
            "weight for Underweight, and 0 for a full exit (Sell). "
            "Null is correct ONLY for Hold, where no order is placed. "
            "This is the sole AI sizing recommendation; the execution engine still applies hard risk caps."
        ),
    )
    suggested_capital: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Approximate order notional in the portfolio's base currency. It must agree with "
            "position_size_pct and available cash; use 0 for no new order."
        ),
    )
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    recommended_leverage: float = Field(
        default=1.0,
        description=(
            "Final per-stock leverage multiplier for this decision, 1.0 (cash) to "
            "10.0. This is the final Portfolio Manager leverage adjusted for the risk "
            "debate outcome and the persona's risk tolerance. Conservative personas "
            "should cap this near 1.0; only use elevated leverage on high-conviction "
            "ratings (Buy) for liquid instruments with a defined stop-loss."
        ),
    )
    liquidation_price: float | None = Field(
        default=None,
        description=(
            "Optional approximate price at which a leveraged long would be "
            "force-liquidated, for the user's awareness. Leave null when leverage is 1.0."
        ),
    )
    time_horizon: str | None = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )

def render_pm_decision(decision: PortfolioDecision, output_language: str | None = None) -> str:
    labels = report_texts(
        (
            "rating",
            "executive_summary",
            "investment_thesis",
            "confidence_score",
            "entry_price",
            "stop_loss",
            "take_profit",
            "position_sizing",
            "suggested_capital",
            "price_target",
            "recommended_leverage",
            "liquidation_price",
            "time_horizon",
        ),
        output_language,
    )
    parts = [
        f"**{labels['rating']}**: {report_rating(decision.rating.value, output_language)}",
        "",
        f"**{labels['executive_summary']}**: {decision.executive_summary}",
        "",
        f"**{labels['investment_thesis']}**: {decision.investment_thesis}",
        "",
        f"**{labels['confidence_score']}**: {decision.confidence_score:.0%}",
    ]
    if decision.entry_price is not None:
        parts.extend(["", f"**{labels['entry_price']}**: {decision.entry_price}"])
    if decision.stop_loss is not None:
        parts.extend(["", f"**{labels['stop_loss']}**: {decision.stop_loss}"])
    if decision.take_profit_price is not None:
        parts.extend(["", f"**{labels['take_profit']}**: {decision.take_profit_price}"])
    if decision.position_size_pct is not None:
        parts.extend(["", f"**{labels['position_sizing']}**: {decision.position_size_pct:.1f}%"])
    if decision.suggested_capital is not None:
        parts.extend(["", f"**{labels['suggested_capital']}**: {decision.suggested_capital:,.2f}"])
    if decision.price_target is not None:
        parts.extend(["", f"**{labels['price_target']}**: {decision.price_target}"])
    if decision.recommended_leverage and abs(decision.recommended_leverage - 1.0) > 1e-9:
        parts.extend(["", f"**{labels['recommended_leverage']}**: {decision.recommended_leverage:.1f}x"])
    if decision.liquidation_price is not None:
        parts.extend(["", f"**{labels['liquidation_price']}**: {decision.liquidation_price}"])
    if decision.time_horizon:
        parts.extend(["", f"**{labels['time_horizon']}**: {decision.time_horizon}"])
    return "\n".join(parts)

class PropagateResult(BaseModel):
    ticker: str
    trade_date: str
    asset_type: str = "stock"
    signal: str
    market_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    fundamentals_report: str = ""
    macro_report: str = ""
    options_report: str = ""
    quant_report: str = ""
    earnings_report: str = ""
    insider_report: str = ""
    ownership_report: str = ""
    ratings_report: str = ""
    short_interest_report: str = ""
    valuation_report: str = ""
    catalyst_report: str = ""
    review_report: str = ""
    synthesis_report: str = ""
    audit_report: str = ""
    investment_plan: str = ""
    analysis_plan_json: dict[str, Any] = Field(default_factory=dict)
    synthesis_json: dict[str, Any] = Field(default_factory=dict)
    market_regime_json: dict[str, Any] = Field(default_factory=dict)
    strategy_candidate_json: dict[str, Any] = Field(default_factory=dict)
    pm_proposal_json: dict[str, Any] = Field(default_factory=dict)
    portfolio_decision_json: dict[str, Any] | str = Field(default_factory=dict)
    decision_transition_json: dict[str, Any] = Field(default_factory=dict)
    calibrated_confidence: float | None = None
    final_decision: str = ""

    @classmethod
    def from_state(cls, state: dict, signal: str) -> PropagateResult:
        from backend.trading_agents.agents.runtime.agent_states import StateKeys

        return cls(
            ticker=state.get(StateKeys.COMPANY, ""),
            trade_date=state.get(StateKeys.TRADE_DATE, ""),
            asset_type=state.get(StateKeys.ASSET_TYPE, "stock"),
            signal=signal,
            market_report=state.get(StateKeys.MARKET_REPORT, ""),
            sentiment_report=state.get(StateKeys.SENTIMENT_REPORT, ""),
            news_report=state.get(StateKeys.NEWS_REPORT, ""),
            fundamentals_report=state.get(StateKeys.FUNDAMENTALS_REPORT, ""),
            macro_report=state.get(StateKeys.MACRO_REPORT, ""),
            options_report=state.get(StateKeys.OPTIONS_REPORT, ""),
            quant_report=state.get(StateKeys.QUANT_REPORT, ""),
            earnings_report=state.get(StateKeys.EARNINGS_REPORT, ""),
            insider_report=state.get(StateKeys.INSIDER_REPORT, ""),
            ownership_report=state.get(StateKeys.OWNERSHIP_REPORT, ""),
            ratings_report=state.get(StateKeys.RATINGS_REPORT, ""),
            short_interest_report=state.get(StateKeys.SHORT_INTEREST_REPORT, ""),
            valuation_report=state.get(StateKeys.VALUATION_REPORT, ""),
            catalyst_report=state.get(StateKeys.CATALYST_REPORT, ""),
            review_report=state.get(StateKeys.REVIEW_REPORT, ""),
            synthesis_report=state.get(StateKeys.SYNTHESIS_REPORT, ""),
            audit_report=state.get(StateKeys.AUDIT_REPORT, ""),
            investment_plan=state.get(StateKeys.INVESTMENT_PLAN, ""),
            analysis_plan_json=state.get(StateKeys.ANALYSIS_PLAN_JSON, {}) or {},
            synthesis_json=state.get(StateKeys.SYNTHESIS_JSON, {}) or {},
            market_regime_json=state.get(StateKeys.MARKET_REGIME_JSON, {}) or {},
            strategy_candidate_json=state.get(StateKeys.STRATEGY_CANDIDATE_JSON, {}) or {},
            pm_proposal_json=state.get(StateKeys.PM_PROPOSAL_JSON, {}) or {},
            portfolio_decision_json=state.get(StateKeys.PORTFOLIO_DECISION_JSON, "{}"),
            decision_transition_json=state.get(StateKeys.DECISION_TRANSITION_JSON, {}) or {},
            calibrated_confidence=state.get(StateKeys.CALIBRATED_CONFIDENCE),
            final_decision=state.get(StateKeys.FINAL_TRADE_DECISION, ""),
        )
