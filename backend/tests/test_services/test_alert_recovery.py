from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import alert_service


class _SessionContext:
    """Expose a fake session through AsyncSessionLocal's context-manager API."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_args) -> bool:
        return False

class _Scalars:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows

class _Result:
    def __init__(self, *, rows=None, scalar=None) -> None:
        self._rows = rows
        self._scalar = scalar

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar

class _RecoverySession:
    def __init__(self, alerts, analysis_ids) -> None:
        self._alerts = alerts
        self._analysis_ids = iter(analysis_ids)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result(rows=self._alerts)
        return _Result(scalar=next(self._analysis_ids))

def _triggered_alert(*, user_id: int, ticker: str = "AAPL"):
    return SimpleNamespace(
        user_id=user_id,
        ticker=ticker,
        triggered_at=datetime(2026, 7, 28, tzinfo=UTC),
    )

async def test_recovery_accepts_multiple_existing_alert_analyses(monkeypatch):
    """Recovery checks existence; duplicate historical rows are not an error."""
    session = _RecoverySession([_triggered_alert(user_id=7)], [101])

    throttled_analyze = AsyncMock()
    monkeypatch.setattr(alert_service, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(alert_service, "_throttled_analyze", throttled_analyze)
    # check_and_recover_lost_alerts() drains the outbox first; that path has its
    # own coverage and would otherwise consume this fake session's statements.
    monkeypatch.setattr(alert_service, "process_alert_outbox", AsyncMock())

    await alert_service.check_and_recover_lost_alerts()

    throttled_analyze.assert_not_awaited()
    assert "analysis_results.id" in str(session.statements[1])
    assert "LIMIT" in str(session.statements[1])

async def test_recovery_deduplicates_identical_alert_targets(monkeypatch):
    """Two triggered alerts for one target must not launch two recovery jobs."""
    session = _RecoverySession([_triggered_alert(user_id=7), _triggered_alert(user_id=7)], [None, None])

    throttled_analyze = AsyncMock()
    monkeypatch.setattr(alert_service, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(alert_service, "_throttled_analyze", throttled_analyze)
    # check_and_recover_lost_alerts() drains the outbox first; that path has its
    # own coverage and would otherwise consume this fake session's statements.
    monkeypatch.setattr(alert_service, "process_alert_outbox", AsyncMock())

    await alert_service.check_and_recover_lost_alerts()

    throttled_analyze.assert_awaited_once_with("AAPL", "2026-07-28", 7, alert_service._RECOVERY_SEMAPHORE)
