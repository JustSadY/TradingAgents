"""The declared event vocabulary must match what the code actually emits.

`schemas/analysis_events.AnalysisEventType` is published through `/api/meta`
and drives a frontend test that asserts the browser handles every member. That
only means anything if the union stays in step with the emitters, and nothing
about a dict literal forces it to.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.schemas.analysis_events import ANALYSIS_EVENT_TYPES

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Where analysis progress events are constructed. Restricted to these modules
# because `"type"` is an ordinary key elsewhere — LLM message parts, chart
# patterns and tool settings all use it for something unrelated.
EMITTING_MODULES = (
    "services/analysis/emitter.py",
    "services/analysis/orchestrator.py",
    "services/analysis/streaming_handler.py",
    "services/analysis_service.py",
)

EVENT_LITERAL = re.compile(r'"type":\s*"([a-z_]+)"')


def emitted_event_types() -> set[str]:
    found: set[str] = set()
    for relative in EMITTING_MODULES:
        source = (BACKEND_ROOT / relative).read_text()
        found.update(EVENT_LITERAL.findall(source))
    return found


def test_every_emitted_event_type_is_declared():
    undeclared = emitted_event_types() - set(ANALYSIS_EVENT_TYPES)

    assert undeclared == set(), (
        f"emitted but not in AnalysisEventType: {sorted(undeclared)}. "
        "Declare it, then handle it in the browser."
    )


def test_the_scan_finds_events_at_all():
    """Guards the module list above: a rename would otherwise pass vacuously."""
    emitted = emitted_event_types()

    assert len(emitted) >= 10
    assert {"complete", "error", "report", "stall_warning"} <= emitted


def test_declared_types_are_unique():
    assert len(ANALYSIS_EVENT_TYPES) == len(set(ANALYSIS_EVENT_TYPES))
