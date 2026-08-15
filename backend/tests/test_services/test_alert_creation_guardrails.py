from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.services.alert_creation_service import (
    ALERT_SOURCE_ANALYSIS,
    AlertGuardrailViolation,
    create_alert_with_guardrails,
    rearm_alert_with_guardrails,
)
from backend.services.settings_service import get_or_create_settings


async def _settings(db: AsyncSession, user: User, **values):
    settings = await get_or_create_settings(db, user)
    for field, value in values.items():
        setattr(settings, field, value)
    await db.flush()
    return settings

async def test_manual_alerts_obey_active_cap_but_not_ai_controls(db: AsyncSession, test_user: User):
    await _settings(db, test_user, max_active_alerts=2, max_ai_alerts_per_run=0, ai_alert_cooldown_hours=720)

    first = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="above",
        target_price=200,
        auto_analyze=False,
    )
    second = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="above",
        target_price=200,
        auto_analyze=False,
    )
    assert first is not None and second is not None
    assert first.creation_source == "manual"
    assert second.creation_source == "manual"

    with pytest.raises(AlertGuardrailViolation, match=r"active alert limit \(2\)") as error:
        await create_alert_with_guardrails(
            db,
            user_id=test_user.id,
            ticker="MSFT",
            condition="below",
            target_price=300,
            auto_analyze=False,
        )
    assert error.value.code == "active_limit"

async def test_ai_alert_limit_is_scoped_to_one_analysis_run(db: AsyncSession, test_user: User):
    await _settings(db, test_user, max_active_alerts=10, max_ai_alerts_per_run=2, ai_alert_cooldown_hours=24)

    for target_price in (100, 99):
        created = await create_alert_with_guardrails(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            condition="below",
            target_price=target_price,
            auto_analyze=True,
            alert_type="support",
            creation_source=ALERT_SOURCE_ANALYSIS,
            creation_run_id="analysis-1",
        )
        assert created is not None
        assert created.creation_run_id == "analysis-1"

    skipped = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="below",
        target_price=98,
        auto_analyze=True,
        alert_type="support",
        creation_source=ALERT_SOURCE_ANALYSIS,
        creation_run_id="analysis-1",
        skip_if_limited=True,
    )
    assert skipped is None

    next_run = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="NVDA",
        condition="below",
        target_price=100,
        auto_analyze=True,
        alert_type="support",
        creation_source=ALERT_SOURCE_ANALYSIS,
        creation_run_id="analysis-2",
    )
    assert next_run is not None

async def test_ai_equivalent_alert_cooldown_crosses_runs(db: AsyncSession, test_user: User):
    await _settings(db, test_user, max_active_alerts=10, max_ai_alerts_per_run=3, ai_alert_cooldown_hours=24)

    first = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="below",
        target_price=180,
        auto_analyze=True,
        alert_type="support",
        creation_source=ALERT_SOURCE_ANALYSIS,
        creation_run_id="analysis-1",
    )
    assert first is not None

    with pytest.raises(AlertGuardrailViolation, match="within the last 24 hour") as error:
        await create_alert_with_guardrails(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            condition="below",
            target_price=175,
            auto_analyze=True,
            alert_type="support",
            creation_source=ALERT_SOURCE_ANALYSIS,
            creation_run_id="analysis-2",
        )
    assert error.value.code == "ai_cooldown"

async def test_zero_ai_limit_disables_only_automatic_generation(db: AsyncSession, test_user: User):
    await _settings(db, test_user, max_active_alerts=10, max_ai_alerts_per_run=0, ai_alert_cooldown_hours=0)

    skipped = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="below",
        target_price=180,
        auto_analyze=True,
        alert_type="support",
        creation_source=ALERT_SOURCE_ANALYSIS,
        creation_run_id="analysis-1",
        skip_if_limited=True,
    )
    manual = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="below",
        target_price=180,
        auto_analyze=False,
    )
    assert skipped is None
    assert manual is not None

async def test_rearming_cannot_bypass_active_cap(db: AsyncSession, test_user: User):
    await _settings(db, test_user, max_active_alerts=1, max_ai_alerts_per_run=3, ai_alert_cooldown_hours=0)

    first = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="AAPL",
        condition="above",
        target_price=200,
        auto_analyze=False,
    )
    assert first is not None
    first.enabled = False
    await db.flush()

    second = await create_alert_with_guardrails(
        db,
        user_id=test_user.id,
        ticker="MSFT",
        condition="above",
        target_price=500,
        auto_analyze=False,
    )
    assert second is not None

    with pytest.raises(AlertGuardrailViolation, match=r"active alert limit \(1\)"):
        await rearm_alert_with_guardrails(db, first)

async def test_analysis_source_requires_a_run_id(db: AsyncSession, test_user: User):
    await _settings(db, test_user)
    with pytest.raises(ValueError, match="require an analysis run ID"):
        await create_alert_with_guardrails(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            condition="below",
            target_price=180,
            auto_analyze=True,
            creation_source=ALERT_SOURCE_ANALYSIS,
        )

class _AssistantSession:
    """Fake session for the assistant's confirm-pending-action path.

    The first ``execute`` serves the pending-action SELECT; the second is the
    conditional claim UPDATE, which must report exactly one affected row.
    """

    def __init__(self, row) -> None:
        self._row = row
        self._calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        self._calls += 1
        if self._calls == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self._row)
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        return None

    async def rollback(self):
        return None

def _pending_alert_action(user_id: int = 7):
    return SimpleNamespace(
        id="a" * 32,
        user_id=user_id,
        action="create_price_alert",
        payload={"ticker": "AAPL", "condition": "above", "target_price": 200.0},
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

async def test_assistant_preview_does_not_create_an_alert(monkeypatch):
    """The tool stages a confirmation instead of creating the alert.

    This is the fail-closed contract: nothing is written until the user approves
    a specific action ID.
    """
    from backend.services import alert_creation_service, portfolio_assistant_service

    called = False

    async def _unexpected(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(alert_creation_service, "create_alert_with_guardrails", _unexpected)
    monkeypatch.setattr(
        portfolio_assistant_service,
        "_create_pending_action",
        AsyncMock(return_value="b" * 32),
    )

    message = await portfolio_assistant_service._tool_create_price_alert(
        SimpleNamespace(id=7, is_admin=False),
        {"alerts"},
        "aapl",
        "above",
        200,
    )

    assert not called
    assert "Nothing has been created" in message
    assert "b" * 32 in message

async def test_assistant_confirmation_uses_the_assistant_guardrail_source(monkeypatch):
    """Confirmed assistant alerts must be tagged so their own limits apply."""
    from backend.core import database
    from backend.services import alert_creation_service, portfolio_assistant_service

    captured: dict[str, object] = {}

    async def reject(*_args, **kwargs):
        captured.update(kwargs)
        raise AlertGuardrailViolation("active_limit", "Your active alert limit (1) has been reached.")

    session = _AssistantSession(_pending_alert_action())
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(alert_creation_service, "create_alert_with_guardrails", reject)

    message = await portfolio_assistant_service._tool_confirm_pending_action(
        SimpleNamespace(id=7, is_admin=False),
        {"alerts"},
        "a" * 32,
    )

    assert captured["creation_source"] == "assistant"
    # The confirm path funnels every failure into one generic reply, so the
    # specific limit text is logged rather than surfaced to the user.
    assert message == "The confirmed action was rejected or could not be completed safely."
