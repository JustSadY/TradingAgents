from pathlib import Path


def test_alert_creation_service_does_not_own_guardrail_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "alert_creation_service.py").read_text()

    assert "from sqlalchemy import" not in source
    assert "backend.models.alert" not in source
    assert "backend.models.settings" not in source
    assert "select(PriceAlert" not in source
    assert "select(AppSettings" not in source
    assert "func.count" not in source
    assert "lock_user_alert_settings" in source
    assert "count_active_alerts" in source
    assert "recent_equivalent_analysis_alert_exists" in source
    assert "rearm_alert_row" in source
