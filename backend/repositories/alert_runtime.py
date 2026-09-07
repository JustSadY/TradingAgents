from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.models.alert_outbox import AlertOutbox
from backend.models.analysis import AnalysisResult


async def claim_alert_and_enqueue_outbox(
    db: AsyncSession,
    *,
    alert_id: int,
    user_id: int | None,
    current_value: float | None,
    triggered_at: datetime,
) -> bool:
    """Atomically claim an enabled alert and stage its durable outbox row.

    The caller owns commit/rollback so the service can keep transaction timing
    explicit while persistence details stay inside the repository layer.
    """
    result = await db.execute(
        update(PriceAlert)
        .where(
            PriceAlert.id == alert_id,
            PriceAlert.enabled.is_(True),
            PriceAlert.triggered_at.is_(None),
        )
        .values(triggered_at=triggered_at, enabled=False)
    )
    if not result.rowcount:
        return False

    db.add(
        AlertOutbox(
            alert_id=alert_id,
            user_id=user_id,
            current_value=str(current_value) if current_value is not None else None,
            status="pending",
        )
    )
    await db.flush()
    return True


async def claim_outbox_batch(
    db: AsyncSession,
    *,
    limit: int,
    stale_before: datetime,
    claimed_at: datetime,
) -> list[tuple[int, int | None]]:
    """Lock pending/stale outbox rows and mark them processing."""
    rows = await db.execute(
        select(AlertOutbox)
        .where(
            or_(
                AlertOutbox.status == "pending",
                (AlertOutbox.status == "processing") & (AlertOutbox.claimed_at < stale_before),
            )
        )
        .order_by(AlertOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    items = list(rows.scalars().all())
    claimed: list[tuple[int, int | None]] = []
    for item in items:
        item.status = "processing"
        item.claimed_at = claimed_at
        item.attempts = (item.attempts or 0) + 1
        claimed.append((item.id, item.user_id))
    await db.flush()
    return claimed


async def get_outbox_item_for_update(db: AsyncSession, item_id: int) -> AlertOutbox | None:
    result = await db.execute(select(AlertOutbox).where(AlertOutbox.id == item_id).with_for_update())
    return result.scalar_one_or_none()


async def get_outbox_item(db: AsyncSession, item_id: int) -> AlertOutbox | None:
    return await db.get(AlertOutbox, item_id)


async def get_alert_unscoped(db: AsyncSession, alert_id: int) -> PriceAlert | None:
    return await db.get(PriceAlert, alert_id)


async def complete_outbox_item(
    db: AsyncSession,
    item: AlertOutbox,
    *,
    completed_at: datetime,
) -> None:
    item.status = "completed"
    item.completed_at = completed_at
    item.last_error = None
    await db.flush()


async def mark_outbox_delivery_failure(
    db: AsyncSession,
    item: AlertOutbox,
    *,
    error: str,
    max_attempts: int = 10,
) -> None:
    item.status = "pending" if item.attempts < max_attempts else "failed"
    item.last_error = error[:1000]
    await db.flush()


async def list_triggered_auto_analyze_alerts(db: AsyncSession) -> list[PriceAlert]:
    result = await db.execute(
        select(PriceAlert)
        .where(PriceAlert.triggered_at.isnot(None))
        .where(PriceAlert.auto_analyze.is_(True))
    )
    return list(result.scalars().all())


async def existing_alert_analysis_keys(
    db: AsyncSession,
    keys: set[tuple[str, str, int | None]],
) -> set[tuple[str, str, int | None]]:
    """Return alert-analysis identities already persisted using one query.

    Recovery used to issue one ``EXISTS`` query per triggered alert. The broad
    SQL predicates below keep the query portable across PostgreSQL and SQLite;
    the exact tuple membership check in Python removes any cross-product rows.
    """
    if not keys:
        return set()

    tickers = {ticker for ticker, _trade_date, _user_id in keys}
    trade_dates = {trade_date for _ticker, trade_date, _user_id in keys}
    user_ids = {user_id for _ticker, _trade_date, user_id in keys if user_id is not None}
    include_system = any(user_id is None for _ticker, _trade_date, user_id in keys)

    user_filters = []
    if user_ids:
        user_filters.append(AnalysisResult.user_id.in_(user_ids))
    if include_system:
        user_filters.append(AnalysisResult.user_id.is_(None))

    query = (
        select(AnalysisResult.ticker, AnalysisResult.trade_date, AnalysisResult.user_id)
        .where(AnalysisResult.triggered_by == "alert")
        .where(AnalysisResult.ticker.in_(tickers))
        .where(AnalysisResult.trade_date.in_(trade_dates))
        .where(or_(*user_filters))
    )
    rows = (await db.execute(query)).all()
    return {
        (str(ticker), str(trade_date), user_id)
        for ticker, trade_date, user_id in rows
        if (str(ticker), str(trade_date), user_id) in keys
    }


async def alert_analysis_exists(
    db: AsyncSession,
    *,
    ticker: str,
    trade_date: str,
    user_id: int | None,
) -> bool:
    query = (
        select(AnalysisResult.id)
        .where(AnalysisResult.ticker == ticker)
        .where(AnalysisResult.trade_date == trade_date)
        .where(AnalysisResult.user_id == user_id)
        .where(AnalysisResult.triggered_by == "alert")
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none() is not None
