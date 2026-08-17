from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.models.alert_outbox import AlertOutbox
from backend.models.user import User
from backend.repositories.alert_runtime import (
    claim_alert_and_enqueue_outbox,
    claim_outbox_batch,
    get_outbox_item,
    mark_outbox_delivery_failure,
)


async def test_claim_alert_stages_one_durable_outbox_row(
    db: AsyncSession,
    test_user: User,
) -> None:
    alert = PriceAlert(
        user_id=test_user.id,
        ticker="AAPL",
        condition="above",
        target_price=200,
        auto_analyze=False,
    )
    db.add(alert)
    await db.flush()

    now = datetime.now(UTC)
    claimed = await claim_alert_and_enqueue_outbox(
        db,
        alert_id=alert.id,
        user_id=test_user.id,
        current_value=201.5,
        triggered_at=now,
    )
    await db.commit()

    assert claimed is True
    await db.refresh(alert)
    assert alert.enabled is False
    assert alert.triggered_at is not None

    from sqlalchemy import select

    row = (
        await db.execute(select(AlertOutbox).where(AlertOutbox.alert_id == alert.id))
    ).scalar_one()
    assert row.user_id == test_user.id
    assert row.current_value == "201.5"
    assert row.status == "pending"


async def test_claim_alert_is_idempotent_after_first_claim(
    db: AsyncSession,
    test_user: User,
) -> None:
    alert = PriceAlert(
        user_id=test_user.id,
        ticker="MSFT",
        condition="below",
        target_price=300,
        auto_analyze=False,
    )
    db.add(alert)
    await db.flush()

    now = datetime.now(UTC)
    first = await claim_alert_and_enqueue_outbox(
        db,
        alert_id=alert.id,
        user_id=test_user.id,
        current_value=299.0,
        triggered_at=now,
    )
    await db.commit()
    second = await claim_alert_and_enqueue_outbox(
        db,
        alert_id=alert.id,
        user_id=test_user.id,
        current_value=298.0,
        triggered_at=now + timedelta(seconds=1),
    )

    assert first is True
    assert second is False


async def test_outbox_retry_policy_is_persisted_in_repository(
    db: AsyncSession,
    test_user: User,
) -> None:
    alert = PriceAlert(
        user_id=test_user.id,
        ticker="NVDA",
        condition="above",
        target_price=150,
        auto_analyze=False,
    )
    db.add(alert)
    await db.flush()
    item = AlertOutbox(alert_id=alert.id, user_id=test_user.id, status="processing", attempts=9)
    db.add(item)
    await db.flush()

    await mark_outbox_delivery_failure(db, item, error="boom", max_attempts=10)
    assert item.status == "pending"
    item.attempts = 10
    await mark_outbox_delivery_failure(db, item, error="still boom", max_attempts=10)
    assert item.status == "failed"
    assert item.last_error == "still boom"


async def test_claim_outbox_batch_reclaims_stale_processing_rows(
    db: AsyncSession,
    test_user: User,
) -> None:
    alert = PriceAlert(
        user_id=test_user.id,
        ticker="META",
        condition="above",
        target_price=500,
        auto_analyze=False,
    )
    db.add(alert)
    await db.flush()
    old = datetime.now(UTC) - timedelta(minutes=10)
    item = AlertOutbox(
        alert_id=alert.id,
        user_id=test_user.id,
        status="processing",
        attempts=1,
        claimed_at=old,
    )
    db.add(item)
    await db.flush()

    claimed_at = datetime.now(UTC)
    claimed = await claim_outbox_batch(
        db,
        limit=10,
        stale_before=claimed_at - timedelta(minutes=5),
        claimed_at=claimed_at,
    )

    assert claimed == [(item.id, test_user.id)]
    reloaded = await get_outbox_item(db, item.id)
    assert reloaded is not None
    assert reloaded.status == "processing"
    assert reloaded.attempts == 2
