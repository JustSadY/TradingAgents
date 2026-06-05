"""Helper for assembling analyst report sections into a single prompt block.

The bull/bear researchers and the three risk debators each repeated the same
loop: iterate a ``{state_field: label}`` mapping, keep non-empty reports, and
join them. The label wording differs between agents (it is part of each agent's
prompt), so callers keep their own mapping and only share the loop.
"""
from __future__ import annotations


def build_resources(state, report_fields: dict[str, str]) -> str:
    """Return labelled, newline-separated non-empty reports from ``state``."""
    resources = []
    for field, label in report_fields.items():
        content = state.get(field, "")
        if content and content.strip():
            resources.append(f"{label}:\n{content.strip()}")
    return "\n\n".join(resources)
