"""Report normalization and persistence routing for analysis runs.

The analyst registry is extensible, whereas :class:`AnalysisResult` has a
fixed set of report columns.  Keeping the registry and the persistence layer
in separate hard-coded lists meant a successfully produced built-in report
could be lost between the graph and the database.  This module aligns every
registered report that has a declared ``AnalysisResult`` column and makes an
unsupported plugin key explicit to the caller instead of silently ignoring it.

Provider content blocks and blank terminal responses are normalised before
they reach a ``Text`` column or a WebSocket client.  A missing terminal
response is represented as a visible degraded report so the user and the
run-quality score can distinguish it from an analyst that was disabled.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

# These are report-shaped artifacts produced after the analyst subgraph.  They
# have real ``AnalysisResult`` columns and should stream exactly like analyst
# reports rather than relying on a separate, stale hard-coded stream list.
PIPELINE_REPORT_FIELDS: tuple[str, ...] = (
    "agent_qa_report",
    "synthesis_report",
    "audit_report",
    "investment_plan",
    "final_trade_decision",
    "portfolio_decision_json",
)


# State names used by the graph are intentionally more descriptive than one
# legacy database column (``final_trade_decision`` → ``final_decision``).
TERMINAL_REPORT_COLUMN_ALIASES: dict[str, str] = {
    "agent_qa_report": "agent_qa_report",
    "synthesis_report": "synthesis_report",
    "audit_report": "audit_report",
    "investment_plan": "investment_plan",
    "final_trade_decision": "final_decision",
}


def persistence_column_for_report(report_key: str) -> str:
    """Return the explicit ``AnalysisResult`` column for a streamed report."""

    return TERMINAL_REPORT_COLUMN_ALIASES.get(report_key, report_key)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def registered_analyst_report_fields() -> tuple[str, ...]:
    """Return registered analyst report state keys at runtime.

    Imports happen lazily: extension analysts are registered while the agent
    package is loaded, and import-time snapshots are exactly what caused prior
    registry/persistence drift.
    """

    from backend.trading_agents.agents.analyst_registry import all_report_keys

    return _dedupe(all_report_keys())


def report_stream_fields() -> tuple[str, ...]:
    """All report artifacts that should be emitted as complete WS sections."""

    return _dedupe((*registered_analyst_report_fields(), *PIPELINE_REPORT_FIELDS))


def report_text(value: Any) -> str:
    """Coerce common provider content variants to displayable plain text.

    Most adapters return ``str``.  Some function/fallback adapters return a
    content-block list or a ``{"text": ...}`` fragment instead.  Passing such
    values into a SQL ``Text`` field can abort the entire analysis; recursively
    extracting their text here keeps the report visible and makes the database
    write type-safe.
    """

    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [report_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, Mapping):
        for key in ("text", "content"):
            if key in value:
                extracted = report_text(value.get(key))
                if extracted:
                    return extracted
        try:
            return json.dumps(value, ensure_ascii=False, default=str).strip()
        except (TypeError, ValueError):
            return str(value).strip()
    content = getattr(value, "content", None)
    if content is not None and content is not value:
        return report_text(content)
    return str(value).strip()


def _report_label(report_key: str) -> str:
    try:
        from backend.trading_agents.agents.analyst_registry import get_report_fields

        label = get_report_fields().get(report_key)
        if isinstance(label, str) and label.strip():
            return label.strip()
    except Exception:
        # Error presentation must never make a completed run fail.
        pass
    return report_key.removesuffix("_report").replace("_", " ").title()


def unavailable_report(report_key: str) -> str:
    """A diagnostic terminal value for a selected analyst with no report."""

    return (
        f"⚠️ {_report_label(report_key)} report unavailable: no readable final report was produced. "
        "No conclusion was inferred; retry this analysis or choose another model."
    )


def normalise_selected_analyst_reports(
    state: Mapping[str, Any],
    selected_analysts: Iterable[str],
    *,
    is_enabled: Callable[[str], bool] | None = None,
) -> dict[str, str]:
    """Return terminal text for every *active* selected analyst.

    Disabled analysts intentionally remain absent.  An enabled analyst that
    ran but ends with an empty/non-text result instead receives a visible
    degraded report.  This prevents a blank panel from being mistaken for a
    successful analysis and ensures the quality score captures the failure.
    """

    from backend.trading_agents.agents.analyst_registry import report_key_for

    out: dict[str, str] = {}
    for analyst_key in selected_analysts:
        if is_enabled is not None and not is_enabled(analyst_key):
            continue
        report_key = report_key_for(analyst_key)
        if not report_key:
            continue
        text = report_text(state.get(report_key))
        out[report_key] = text or unavailable_report(report_key)
    return out


def analysis_result_report_columns() -> frozenset[str]:
    """The ``AnalysisResult`` text columns available to store report content."""

    from backend.models.analysis import AnalysisResult

    return frozenset(AnalysisResult.__table__.columns.keys())


def persisted_registered_report_fields() -> tuple[str, ...]:
    """Registered analyst fields that have an explicit database column.

    A plugin report must receive an intentional schema/API addition before it
    becomes durable.  Returning only declared columns prevents the repository
    layer's ``hasattr`` guard from silently accepting a value that it then
    drops.
    """

    columns = analysis_result_report_columns()
    return tuple(key for key in registered_analyst_report_fields() if key in columns)


def terminal_report_column_values(
    state: Mapping[str, Any],
    analyst_reports: Mapping[str, str],
) -> dict[str, str]:
    """Build the non-empty report subset for a terminal DB update.

    Incremental streaming may already have saved a useful report.  Omitting an
    empty final value is deliberate: a resumed/malformed final state must not
    overwrite that durable text with ``''``.  The skeleton row supplies empty
    defaults for reports that never arrived.
    """

    columns = analysis_result_report_columns()
    values = {key: text for key, text in analyst_reports.items() if key in columns and text}
    for state_key, column_key in TERMINAL_REPORT_COLUMN_ALIASES.items():
        text = report_text(state.get(state_key))
        if text and column_key in columns:
            values[column_key] = text
    return values
