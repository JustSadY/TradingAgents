from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.password_hashing import hash_password
from backend.models.alert import PriceAlert
from backend.models.user import User
from backend.services.alert_management_service import (
    AlertUpdateValidationError,
    delete_user_alert,
    update_user_alert,
)


async def _alert(db: AsyncSession, *, user_id: int, alert_type: str, target: str = "10") -> PriceAlert:
    row = PriceAlert(
        user_id=user_id,
        ticker="AAPL",
        alert_type=alert_type,
        condition="above",
        target_price=Decimal(target),
        auto_analyze=False,
        enabled=True,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_update_user_alert_keeps_type_validation_out_of_router(db: AsyncSession, test_user: User):
    alert = await _alert(db, user_id=test_user.id, alert_type="rsi", target="70")

    with pytest.raises(AlertUpdateValidationError, match="between 0 and 100"):
        await update_user_alert(
            db,
            user=test_user,
            alert_id=alert.id,
            changes={"target_price": 101.0},
        )


@pytest.mark.asyncio
async def test_update_user_alert_normalizes_macd_target(db: AsyncSession, test_user: User):
    alert = await _alert(db, user_id=test_user.id, alert_type="macd_cross", target="0")

    updated = await update_user_alert(
        db,
        user=test_user,
        alert_id=alert.id,
        changes={"target_price": 25.0, "auto_analyze": True},
    )

    assert updated is not None
    assert updated.target_price == Decimal("0")
    assert updated.auto_analyze is True


@pytest.mark.asyncio
async def test_delete_user_alert_refuses_another_tenants_row(db: AsyncSession, test_user: User):
    other = User(
        username="alert-other",
        hashed_password=hash_password("pass"),
        email="alert-other@example.com",
        role="user",
        is_active=True,
    )
    db.add(other)
    await db.flush()
    theirs = await _alert(db, user_id=other.id, alert_type="price", target="150")

    deleted = await delete_user_alert(db, user=test_user, alert_id=theirs.id)

    assert deleted is False
    assert await db.get(PriceAlert, theirs.id) is not None


def test_alert_management_service_does_not_persist_fields_directly() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "alert_management_service.py").read_text()

    assert "setattr(alert" not in source
    assert "await db.flush()" not in source
    assert "apply_alert_changes" in source
