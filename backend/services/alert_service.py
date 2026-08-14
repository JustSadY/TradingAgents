import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import or_, select, update

from backend.core.database import AsyncSessionLocal
from backend.models.alert import PriceAlert
from backend.models.alert_outbox import AlertOutbox
from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.services.market_data_service import get_live_prices_batch
from backend.services.notification_service import notify_alert_triggered
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_RECOVERY_SEMAPHORE = asyncio.Semaphore(3)
_ALERT_SEMAPHORE = asyncio.Semaphore(5)

_INDICATOR_ALERT_TYPES = frozenset({"rsi", "macd_cross"})

async def _fetch_alert_market_summary(ticker: str) -> str:
    try:
        import yfinance as yf

        info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
        hist = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="3mo"))

        parts = []
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose")
        if price and prev_close:
            change_pct = ((price - prev_close) / prev_close) * 100
            parts.append(f"Fiyat: ${price:.2f} ({change_pct:+.2f}%)")

        volume = info.get("volume")
        avg_vol = info.get("averageVolume")
        if volume and avg_vol and avg_vol > 0:
            vol_ratio = volume / avg_vol
            parts.append(f"Hacim: {vol_ratio:.1f}x ortalama")

        if hist is not None and len(hist) >= 20:
            from backend.services.indicator_service import calculate_rsi

            rsi_series = calculate_rsi(hist["Close"])
            if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]):
                rsi_val = float(rsi_series.iloc[-1])
                parts.append(f"RSI(14): {rsi_val:.1f}")

        from backend.services.news_service import get_news_feed

        news = await get_news_feed(ticker, 3)
        if news:
            headlines = [n.get("title", "")[:80] for n in news[:3] if n.get("title")]
            if headlines:
                parts.append("Haberler: " + " | ".join(headlines))

        return " | ".join(parts) if parts else ""
    except Exception as exc:
        _logger.warning("Market summary fetch failed for %s: %s", ticker, exc)
        return ""

async def _fetch_close_series(ticker: str, period: str = "6mo"):
    """Daily close-price series for indicator alerts; ``None`` on any failure."""
    try:
        import yfinance as yf

        return await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period=period)["Close"])
    except Exception as exc:  # noqa: BLE001 — never block the alert loop on one bad ticker
        _logger.warning("Indicator alert history fetch failed for %s: %s", ticker, exc)
        return None

async def _check_indicator_alert(alert: PriceAlert) -> tuple[bool, str]:
    """Evaluate an RSI/MACD-cross alert. Returns ``(hit, detail)`` for logging."""
    from backend.services.indicator_service import calculate_macd, calculate_rsi

    hist = await _fetch_close_series(alert.ticker)
    if hist is None or len(hist) < 30:
        return False, ""

    if alert.alert_type == "rsi":
        rsi = calculate_rsi(hist)
        if rsi.empty or pd.isna(rsi.iloc[-1]):
            return False, ""
        current = float(rsi.iloc[-1])
        threshold = float(alert.target_price)
        hit = (alert.condition == "above" and current >= threshold) or (
            alert.condition == "below" and current <= threshold
        )
        return hit, f"RSI={current:.1f}"

    if alert.alert_type == "macd_cross":
        macd, signal = calculate_macd(hist)
        if len(macd) < 2 or macd.iloc[-2:].isna().any() or signal.iloc[-2:].isna().any():
            return False, ""
        prev_diff = float(macd.iloc[-2] - signal.iloc[-2])
        curr_diff = float(macd.iloc[-1] - signal.iloc[-1])
        bullish_cross = prev_diff <= 0 and curr_diff > 0
        bearish_cross = prev_diff >= 0 and curr_diff < 0
        hit = (alert.condition == "above" and bullish_cross) or (alert.condition == "below" and bearish_cross)
        return hit, f"MACD-signal diff {prev_diff:.3f} -> {curr_diff:.3f}"

    return False, ""

async def _deliver_alert_side_effects(db, alert: PriceAlert, settings, current_value: float | None) -> None:
    """Deliver an already-committed outbox item."""
    summary = await _fetch_alert_market_summary(alert.ticker)
    if summary:
        _logger.info("Alert market summary for %s: %s", alert.ticker, summary)

    user = await db.get(User, alert.user_id) if alert.user_id is not None else None
    if settings and user:
        user_settings = await get_or_create_settings(db, user)
        await notify_alert_triggered(
            alert.ticker,
            alert.condition,
            current_value if current_value is not None else float(alert.target_price),
            user_settings,
            alert_type=getattr(alert, "alert_type", "price"),
            market_summary=summary,
        )

    if alert.auto_analyze and user:
        from backend.services.analysis_queue import dispatch_analysis
        from backend.services.analysis_service import register_queued_task

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        task_id = str(uuid.uuid4())
        user_settings = await get_or_create_settings(db, user)
        from backend.repositories.analysis import create_analysis_result

        await create_analysis_result(
            db, task_id=task_id, user_id=user.id, ticker=alert.ticker, trade_date=today,
            asset_type="stock", status="queued", heartbeat_at=datetime.now(UTC), triggered_by="alert",
        )
        await register_queued_task(
            task_id, ticker=alert.ticker, trade_date=today, asset_type="stock", user_id=user.id
        )
        await dispatch_analysis(
            None,
            ticker=alert.ticker,
            trade_date=today,
            asset_type="stock",
            settings=user_settings,
            task_id=task_id,
            user=user,
            triggered_by="alert",
        )


async def _claim_alert(db, alert: PriceAlert, current_value: float | None) -> bool:
    """Atomically mark one alert and create durable side-effect work."""
    now = datetime.now(UTC)
    result = await db.execute(
        update(PriceAlert)
        .where(PriceAlert.id == alert.id, PriceAlert.enabled.is_(True), PriceAlert.triggered_at.is_(None))
        .values(triggered_at=now, enabled=False)
    )
    if not result.rowcount:
        await db.rollback()
        return False
    db.add(
        AlertOutbox(
            alert_id=alert.id,
            user_id=alert.user_id,
            current_value=str(current_value) if current_value is not None else None,
            status="pending",
        )
    )
    await db.commit()
    return True


async def process_alert_outbox(limit: int = 50) -> None:
    """Retry durable alert deliveries; safe after process crashes."""
    async with AsyncSessionLocal() as db:
        stale_cutoff = datetime.now(UTC).timestamp() - 300
        rows = await db.execute(
            select(AlertOutbox)
            .where(
                or_(
                    AlertOutbox.status == "pending",
                    (AlertOutbox.status == "processing") & (AlertOutbox.claimed_at < datetime.fromtimestamp(stale_cutoff, UTC)),
                )
            )
            .order_by(AlertOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        items = list(rows.scalars().all())
        for item in items:
            item.status = "processing"
            item.claimed_at = datetime.now(UTC)
            item.attempts = (item.attempts or 0) + 1
        await db.commit()

    for item_id in [item.id for item in items]:
        async with AsyncSessionLocal() as delivery_db:
            row = await delivery_db.execute(
                select(AlertOutbox).where(AlertOutbox.id == item_id).with_for_update()
            )
            item = row.scalar_one_or_none()
            if not item or item.status != "processing":
                continue
            alert = await delivery_db.get(PriceAlert, item.alert_id)
            try:
                if not alert:
                    item.status = "completed"
                    item.completed_at = datetime.now(UTC)
                else:
                    from backend.repositories.system_settings import get_system_settings

                    settings = await get_system_settings(delivery_db)
                    value = float(item.current_value) if item.current_value is not None else None
                    await _deliver_alert_side_effects(delivery_db, alert, settings, value)
                    item.status = "completed"
                    item.completed_at = datetime.now(UTC)
                    item.last_error = None
                await delivery_db.commit()
            except Exception as exc:
                await delivery_db.rollback()
                async with AsyncSessionLocal() as failure_db:
                    failed = await failure_db.get(AlertOutbox, item_id)
                    if failed:
                        failed.status = "pending" if failed.attempts < 10 else "failed"
                        failed.last_error = str(exc)[:1000]
                        await failure_db.commit()
                _logger.exception("Alert outbox delivery failed id=%s", item_id)


async def check_price_alerts() -> None:
    async with AsyncSessionLocal() as db:
        from backend.repositories.alerts import get_enabled_alerts

        alerts = await get_enabled_alerts(db)
        if not alerts:
            return

        price_alerts = [a for a in alerts if getattr(a, "alert_type", "price") not in _INDICATOR_ALERT_TYPES]
        indicator_alerts = [a for a in alerts if getattr(a, "alert_type", "price") in _INDICATOR_ALERT_TYPES]

        prices = await get_live_prices_batch([a.ticker for a in price_alerts]) if price_alerts else {}

        for alert in price_alerts:
            price = prices.get(alert.ticker)
            if price is None:
                continue

            hit = (alert.condition == "above" and price >= alert.target_price) or (
                alert.condition == "below" and price <= alert.target_price
            )
            if not hit:
                continue

            _logger.info(
                "Alert triggered: %s %s $%.2f (current: $%.2f)",
                alert.ticker,
                alert.condition,
                alert.target_price,
                price,
            )
            await _claim_alert(db, alert, float(price))

        for alert in indicator_alerts:
            try:
                hit, detail = await _check_indicator_alert(alert)
            except Exception as exc:  # noqa: BLE001 — one bad ticker must not break the loop
                _logger.warning("Indicator alert check failed for %s: %s", alert.ticker, exc)
                continue
            if not hit:
                continue

            _logger.info("Indicator alert triggered: %s %s (%s)", alert.ticker, alert.alert_type, detail)
            await _claim_alert(db, alert, None)

    await process_alert_outbox()

async def _throttled_analyze(ticker: str, trade_date: str, user_id: int | None, semaphore: asyncio.Semaphore) -> None:
    """Acquire *semaphore* before running ``_auto_analyze`` to cap concurrency."""
    async with semaphore:
        await _auto_analyze(ticker, trade_date, user_id)

async def _auto_analyze(ticker: str, trade_date: str, user_id: int | None) -> None:
    try:
        async with AsyncSessionLocal() as new_db:
            result = await new_db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return
            settings = await get_or_create_settings(new_db, user)
            task_id = str(uuid.uuid4())
            from backend.repositories.analysis import create_analysis_result
            from backend.services.analysis_queue import dispatch_analysis
            from backend.services.analysis_service import register_queued_task

            await create_analysis_result(
                new_db, task_id=task_id, user_id=user.id, ticker=ticker, trade_date=trade_date,
                asset_type="stock", status="queued", heartbeat_at=datetime.now(UTC), triggered_by="alert",
            )
            await register_queued_task(
                task_id, ticker=ticker, trade_date=trade_date, asset_type="stock", user_id=user.id
            )
            await dispatch_analysis(
                None,
                ticker=ticker,
                trade_date=trade_date,
                asset_type="stock",
                settings=settings,
                task_id=task_id,
                user=user,
                triggered_by="alert",
            )
    except Exception:
        _logger.exception("Auto-analyze from alert failed %s", ticker)

async def check_and_recover_lost_alerts() -> None:
    await process_alert_outbox()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert)
            .where(PriceAlert.triggered_at.isnot(None))
            .where(PriceAlert.auto_analyze.is_(True))
        )
        triggered_alerts = result.scalars().all()
        missing: list[tuple[str, str, int | None]] = []
        missing_keys: set[tuple[str, str, int | None]] = set()
        for alert in triggered_alerts:
            trigger_date = alert.triggered_at.strftime("%Y-%m-%d")
            res_analysis = await db.execute(
                select(AnalysisResult.id)
                .where(AnalysisResult.ticker == alert.ticker)
                .where(AnalysisResult.trade_date == trigger_date)
                .where(AnalysisResult.user_id == alert.user_id)
                .where(AnalysisResult.triggered_by == "alert")
                .limit(1)
            )
            analysis_id = res_analysis.scalar_one_or_none()
            if analysis_id is None:
                _logger.warning(
                    "Recovering lost alert analysis task for %s (triggered at %s)",
                    alert.ticker,
                    trigger_date,
                )
                recovery_key = (alert.ticker, trigger_date, alert.user_id)
                if recovery_key not in missing_keys:
                    missing_keys.add(recovery_key)
                    missing.append(recovery_key)

        if not missing:
            return

        batch_size = 3
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            await asyncio.gather(
                *[
                    _throttled_analyze(ticker, trade_date, user_id, _RECOVERY_SEMAPHORE)
                    for ticker, trade_date, user_id in batch
                ],
                return_exceptions=True,
            )
            if i + batch_size < len(missing):
                await asyncio.sleep(0.5)
