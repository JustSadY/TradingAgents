from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import alert_service


class _SessionContext:
    """Expose a fake session through trusted background context-manager APIs."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_args) -> bool:
        return False


def _triggered_alert(*, user_id: int, ticker: str = "AAPL"):
    return SimpleNamespace(
        user_id=user_id,
        ticker=ticker,
        triggered_at=datetime(2026, 7, 28, tzinfo=UTC),
    )


async def test_recovery_accepts_existing_alert_analysis(monkeypatch):
    """Recovery checks all candidate identities through one batch lookup."""
    session = object()
    alert = _triggered_alert(user_id=7)
    list_alerts = AsyncMock(return_value=[alert])
    existing_keys = AsyncMock(return_value={("AAPL", "2026-07-28", 7)})
    throttled_analyze = AsyncMock()

    monkeypatch.setattr(alert_service, "trusted_background_session", lambda _cap: _SessionContext(session))
    monkeypatch.setattr(alert_service, "list_triggered_auto_analyze_alerts", list_alerts)
    monkeypatch.setattr(alert_service, "existing_alert_analysis_keys", existing_keys)
    monkeypatch.setattr(alert_service, "_throttled_analyze", throttled_analyze)
    monkeypatch.setattr(alert_service, "process_alert_outbox", AsyncMock())

    await alert_service.check_and_recover_lost_alerts()

    throttled_analyze.assert_not_awaited()
    list_alerts.assert_awaited_once_with(session)
    existing_keys.assert_awaited_once_with(session, {("AAPL", "2026-07-28", 7)})


async def test_recovery_deduplicates_identical_alert_targets_before_batch_lookup(monkeypatch):
    """Duplicate alerts produce one lookup identity and one recovery job."""
    session = object()
    alerts = [_triggered_alert(user_id=7), _triggered_alert(user_id=7)]
    list_alerts = AsyncMock(return_value=alerts)
    existing_keys = AsyncMock(return_value=set())
    throttled_analyze = AsyncMock()

    monkeypatch.setattr(alert_service, "trusted_background_session", lambda _cap: _SessionContext(session))
    monkeypatch.setattr(alert_service, "list_triggered_auto_analyze_alerts", list_alerts)
    monkeypatch.setattr(alert_service, "existing_alert_analysis_keys", existing_keys)
    monkeypatch.setattr(alert_service, "_throttled_analyze", throttled_analyze)
    monkeypatch.setattr(alert_service, "process_alert_outbox", AsyncMock())

    await alert_service.check_and_recover_lost_alerts()

    existing_keys.assert_awaited_once_with(session, {("AAPL", "2026-07-28", 7)})
    throttled_analyze.assert_awaited_once_with(
        "AAPL",
        "2026-07-28",
        7,
        alert_service._RECOVERY_SEMAPHORE,
    )


async def test_recovery_batches_multiple_targets_and_only_recovers_missing(monkeypatch):
    session = object()
    alerts = [
        _triggered_alert(user_id=7, ticker="AAPL"),
        _triggered_alert(user_id=8, ticker="MSFT"),
    ]
    candidates = {("AAPL", "2026-07-28", 7), ("MSFT", "2026-07-28", 8)}
    list_alerts = AsyncMock(return_value=alerts)
    existing_keys = AsyncMock(return_value={("AAPL", "2026-07-28", 7)})
    throttled_analyze = AsyncMock()

    monkeypatch.setattr(alert_service, "trusted_background_session", lambda _cap: _SessionContext(session))
    monkeypatch.setattr(alert_service, "list_triggered_auto_analyze_alerts", list_alerts)
    monkeypatch.setattr(alert_service, "existing_alert_analysis_keys", existing_keys)
    monkeypatch.setattr(alert_service, "_throttled_analyze", throttled_analyze)
    monkeypatch.setattr(alert_service, "process_alert_outbox", AsyncMock())

    await alert_service.check_and_recover_lost_alerts()

    existing_keys.assert_awaited_once_with(session, candidates)
    throttled_analyze.assert_awaited_once_with(
        "MSFT",
        "2026-07-28",
        8,
        alert_service._RECOVERY_SEMAPHORE,
    )


def test_alert_service_does_not_own_background_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "alert_service.py").read_text()

    assert "from sqlalchemy" not in source
    assert "backend.models.alert" not in source
    assert "backend.models.alert_outbox" not in source
    assert "backend.models.analysis" not in source
    assert "backend.models.user" not in source
    assert "select(PriceAlert" not in source
    assert "select(AlertOutbox" not in source
    assert "update(PriceAlert" not in source
    assert "claim_alert_and_enqueue_outbox" in source
    assert "claim_outbox_batch" in source
    assert "list_triggered_auto_analyze_alerts" in source
    assert "existing_alert_analysis_keys" in source


def test_alert_service_keeps_audited_background_capabilities() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "alert_service.py").read_text()

    assert "BackgroundCapability.ALERT_OUTBOX" in source
    assert "BackgroundCapability.ALERT_CHECKER" in source
    assert "BackgroundCapability.ALERT_RECOVERY" in source
    assert "set_user_background_context" in source
