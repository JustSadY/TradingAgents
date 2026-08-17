from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services import analysis_stats_service
from backend.services.confidence_calibration_service import build_calibration_context


async def test_analysis_stats_query_failures_are_not_hidden(monkeypatch) -> None:
    async def fail_query(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(analysis_stats_service, "list_completed_analyses_for_stats", fail_query)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await analysis_stats_service.get_ab_comparison(SimpleNamespace(), user_id=1)


def test_calibration_ignores_removed_chart_annotation_fallback() -> None:
    row = SimpleNamespace(
        portfolio_decision_json=None,
        chart_annotations={
            "portfolio_decision": {
                "rating": "Buy",
                "confidence_score": 0.9,
            }
        },
        signal="Buy",
        alpha_return=0.05,
    )

    context = build_calibration_context([row])

    assert context["total_samples"] == 0
    assert context["total_successes"] == 0


def test_stats_and_tool_settings_services_do_not_own_access_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    stats_source = (backend_root / "services" / "analysis_stats_service.py").read_text()
    tool_settings_source = (backend_root / "services" / "tool_settings_service.py").read_text()

    assert "from sqlalchemy import select" not in stats_source
    assert "backend.models.analysis" not in stats_source
    assert "DB may be unmigrated" not in stats_source
    assert "backend.repositories.analysis_stats" in stats_source

    assert "from sqlalchemy import select" not in tool_settings_source
    assert "UserAgentAccess" not in tool_settings_source
    assert "UserToolAccess" not in tool_settings_source
    assert "UserToolFieldAccess" not in tool_settings_source
    assert "get_user_access_overrides" in tool_settings_source
