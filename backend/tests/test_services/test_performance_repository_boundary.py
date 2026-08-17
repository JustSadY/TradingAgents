from pathlib import Path


def test_performance_service_does_not_own_analysis_or_settings_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "performance_service.py").read_text()

    assert "from sqlalchemy" not in source
    assert "backend.models.analysis" not in source
    assert "backend.models.settings" not in source
    assert "select(AnalysisResult" not in source
    assert "select(AppSettings" not in source
    assert "list_resolved_learning_analyses" in source
    assert "list_return_backfill_candidates" in source
    assert "get_app_settings" in source
