"""Analyst catalog — the single source of truth for selectable analysts.

Each analyst's UI/selection metadata (key, localized label, description, and
whether it is enabled by default) is declared once here. The backend's
``/api/meta`` derives the analyst list from this module so the frontend never
hardcodes it, and the engine graph wiring keys off the same ``key`` values.

Like ``personas.py`` this module is dependency-free and lives at the engine root
so the backend can import it without triggering the heavy ``agents`` package.
Structural wiring (graph nodes, tools, report column) stays with each analyst's
``@register_analyst`` declaration; this catalog is the selection/presentation
metadata.
"""
from __future__ import annotations

from dataclasses import dataclass


from backend.trading_agents.agent_catalog import AGENTS


@dataclass(frozen=True)
class AnalystInfo:
    key: str
    label: str
    description: str
    default_on: bool


ANALYSTS: list[AnalystInfo] = []
for _a in AGENTS:
    if _a.category == "analyst":
        _lbl = _a.label
        if _lbl.endswith(" Analyst"):
            _lbl = _lbl[:-8]
        if _lbl == "Performance Review":
            _lbl = "Review"
        ANALYSTS.append(
            AnalystInfo(
                key=_a.key,
                label=_lbl,
                description=_a.description,
                default_on=_a.default_enabled,
            )
        )

_BY_KEY = {a.key: a for a in ANALYSTS}


def list_analysts() -> list[AnalystInfo]:
    return list(ANALYSTS)


def get_analyst(key: str) -> AnalystInfo | None:
    return _BY_KEY.get(key)


def label_for(key: str) -> str:
    info = _BY_KEY.get(key)
    return info.label if info else key.title()
