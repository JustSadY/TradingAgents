from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.models.user import User
from backend.repositories.alerts import delete_alert_row, get_alert_by_id
from backend.services.alert_creation_service import rearm_alert_with_guardrails


class AlertUpdateValidationError(ValueError):
    """User-facing alert mutation validation failure."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def update_user_alert(
    db: AsyncSession,
    *,
    user: User,
    alert_id: int,
    changes: dict[str, Any],
) -> PriceAlert | None:
    """Apply one authorized alert update and its type-specific policy."""
    alert = await get_alert_by_id(db, alert_id, user=user)
    if alert is None:
        return None

    changes = dict(changes)
    if "target_price" in changes:
        target = float(changes["target_price"])
        if alert.alert_type == "rsi" and not 0 <= target <= 100:
            raise AlertUpdateValidationError("RSI threshold must be between 0 and 100")
        if alert.alert_type == "price" and target <= 0:
            raise AlertUpdateValidationError("Price alerts require a positive target")
        if alert.alert_type == "macd_cross":
            changes["target_price"] = 0.0

    if changes.get("enabled") is True:
        await rearm_alert_with_guardrails(db, alert)
        changes.pop("enabled")

    for field, value in changes.items():
        setattr(alert, field, value)
    await db.flush()
    return alert


async def delete_user_alert(db: AsyncSession, *, user: User, alert_id: int) -> bool:
    """Delete an alert only when it is visible in the caller's tenant scope."""
    alert = await get_alert_by_id(db, alert_id, user=user)
    if alert is None:
        return False
    await delete_alert_row(db, alert)
    return True
