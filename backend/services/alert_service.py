import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pandas as pd

from backend.core.database import AsyncSessionLocal
from backend.core.rls_context import (
    BackgroundCapability,
    set_user_background_context,
    trusted_background_session,
)
from backend.repositories.alert_runtime import (
    claim_alert_and_enqueue_outbox,
    claim_outbox_batch,
    complete_outbox_item,
    existing_alert_analysis_keys,
    get_alert_unscoped,
    get_outbox_item,
    get_outbox_item_for_update,
    list_triggered_auto_analyze_alerts,
    mark_outbox_delivery_failure,
)
from backend.repositories.users import get_user_by_id
from backend.services.market_data_service import get_live_prices_batch
from backend.services.notification_service import notify_alert_triggered
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_RECOVERY_SEMAPHORE = asyncio.Semaphore(3)
_ALERT_SEMAPHORE = asyncio.Semaphore(5)
_OUTBOX_SEMAPHORE = asyncio.Semaphore(3)

_INDICATOR_ALERT_TYPES = frozenset({"rsi", "macd_cross"})

async def _fetch_alert_market_summary(ticker: str) -> str:
    try:
        import yfinance as yf

        from backend.services.news_service import get_news_feed

        info, hist, news = await asyncio.gather(
            asyncio.to_thread(lambda: yf.Ticker(ticker).info),
            asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="3mo")),
            get_news_feed(ticker, 3),
        )

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


def _evaluate_indicator_alert(alert, hist) -> tuple[bool, str]:
    """Evaluate one indicator alert against an already-fetched close series."""
    from backend.services.indicator_service import calculate_macd, calculate_rsi

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
        hit = (alert.condition == "above" and bullish_cross) or (
            alert.condition == "below" and bearish_cross
        )
        return hit, f"MACD-signal diff {prev_diff:.3f} -> {curr_diff:.3f}"

    return False, ""


async def _check_indicator_alert(alert) -> tuple[bool, str]:
    """Compatibility wrapper for evaluating a single indicator alert."""
    hist = await _fetch_close_series(alert.ticker)
    return _evaluate_indicator_alert(alert, hist)


async def _fetch_indicator_histories(alerts) -> dict[str, object]:
    """Fetch one close series per unique indicator ticker with bounded concurrency."""
    tickers = list(dict.fromkeys(alert.ticker for alert in alerts))

    async def _fetch_one(ticker: str):
        async with _ALERT_SEMAPHORE:
            return ticker, await _fetch_close_series(ticker)

    results = await asyncio.gather(*[_fetch_one(ticker) for ticker in tickers])
    return dict(results)


async def _deliver_alert_side_effects(
    db,
    alert,
    settings,
    current_value: float | None,
    *,
    market_summary: str | None = None,
) -> None:
    """Deliver an already-committed outbox item."""
    summary = market_summary if market_summary is not None else await _fetch_alert_market_summary(alert.ticker)
    if summary:
        _logger.info("Alert market summary for %s: %s", alert.ticker, summary)

    user = await get_user_by_id(db, alert.user_id) if alert.user_id is not None else None
    needs_user_settings = user is not None and (settings or alert.auto_analyze)
    user_settings = await get_or_create_settings(db, user) if needs_user_settings else None
    if settings and user and user_settings:
        await notify_alert_triggered(
            alert.ticker,
            alert.condition,
            current_value if current_value is not None else float(alert.target_price),
            user_settings,
            alert_type=getattr(alert, "alert_type", "price"),
            market_summary=summary,
        )

    if alert.auto_analyze and user and user_settings:
        from backend.services.analysis_queue import dispatch_analysis
        from backend.services.analysis_service import register_queued_task

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        task_id = str(uuid.uuid4())
        from backend.repositories.analysis import create_analysis_result

        await create_analysis_result(
            db,
            task_id=task_id,
            user_id=user.id,
            ticker=alert.ticker,
            trade_date=today,
            asset_type="stock",
            status="queued",
            heartbeat_at=datetime.now(UTC),
            triggered_by="alert",
        )
        await register_queued_task(
            task_id,
            ticker=alert.ticker,
            trade_date=today,
            asset_type="stock",
            user_id=user.id,
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


async def _claim_alert(
    db,
    alert_id: int,
    user_id: int | None,
    current_value: float | None,
) -> bool:
    """Atomically mark one alert and create durable side-effect work."""
    claimed = await claim_alert_and_enqueue_outbox(
        db,
        alert_id=alert_id,
        user_id=user_id,
        current_value=current_value,
        triggered_at=datetime.now(UTC),
    )
    if not claimed:
        await db.rollback()
        return False
    await db.commit()
    return True


async def _prepare_outbox_market_summary(db, item_id: int) -> str | None:
    """Read the delivery ticker, release the DB transaction, then do market I/O."""
    item = await get_outbox_item(db, item_id)
    if not item or item.status != "processing":
        await db.rollback()
        return None

    alert = await get_alert_unscoped(db, item.alert_id)
    ticker = str(alert.ticker) if alert and alert.ticker else ""
    # The claim is already durable. End the read transaction before yfinance,
    # news, or other external calls so a worker does not pin a DB connection or
    # row lock while waiting on the network. The item is re-read FOR UPDATE
    # immediately before the actual delivery mutation.
    await db.commit()
    return await _fetch_alert_market_summary(ticker) if ticker else ""


async def _deliver_claimed_outbox_item(item_id: int, user_id: int | None) -> None:
    """Deliver one claimed item in an isolated tenant/system session."""
    async with _OUTBOX_SEMAPHORE:
        if user_id is None:
            async with trusted_background_session(BackgroundCapability.ALERT_OUTBOX) as system_db:
                summary = await _prepare_outbox_market_summary(system_db, item_id)
                if summary is None:
                    return
                await _deliver_outbox_item(system_db, item_id, market_summary=summary)
            return

        async with AsyncSessionLocal() as delivery_db:
            await set_user_background_context(delivery_db, user_id)
            summary = await _prepare_outbox_market_summary(delivery_db, item_id)
            if summary is None:
                return
            await _deliver_outbox_item(delivery_db, item_id, market_summary=summary)


async def process_alert_outbox(limit: int = 50) -> None:
    """Claim globally, then deliver items concurrently in isolated owner contexts."""
    async with trusted_background_session(BackgroundCapability.ALERT_OUTBOX) as db:
        stale_before = datetime.fromtimestamp(datetime.now(UTC).timestamp() - 300, UTC)
        claimed = await claim_outbox_batch(
            db,
            limit=limit,
            stale_before=stale_before,
            claimed_at=datetime.now(UTC),
        )
        await db.commit()

    if not claimed:
        return

    results = await asyncio.gather(
        *[_deliver_claimed_outbox_item(item_id, user_id) for item_id, user_id in claimed],
        return_exceptions=True,
    )
    for (item_id, _user_id), result in zip(claimed, results, strict=True):
        if isinstance(result, BaseException):
            _logger.error("Alert outbox delivery task failed id=%s: %s", item_id, result)


async def _deliver_outbox_item(db, item_id: int, *, market_summary: str | None = None) -> None:
    item = await get_outbox_item_for_update(db, item_id)
    if not item or item.status != "processing":
        return
    item_user_id = item.user_id
    alert = await get_alert_unscoped(db, item.alert_id)
    try:
        if not alert:
            await complete_outbox_item(db, item, completed_at=datetime.now(UTC))
        else:
            from backend.repositories.system_settings import get_system_settings

            settings = await get_system_settings(db)
            value = float(item.current_value) if item.current_value is not None else None
            await _deliver_alert_side_effects(db, alert, settings, value, market_summary=market_summary)
            await complete_outbox_item(db, item, completed_at=datetime.now(UTC))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if item_user_id is not None:
            await set_user_background_context(db, item_user_id)
        failed = await get_outbox_item(db, item_id)
        if failed:
            await mark_outbox_delivery_failure(db, failed, error=str(exc), max_attempts=10)
            await db.commit()
        _logger.exception("Alert outbox delivery failed id=%s", item_id)


async def _claim_alert_for_owner(alert_id: int, user_id: int | None, current_value: float | None) -> bool:
    if user_id is None:
        async with trusted_background_session(BackgroundCapability.ALERT_CHECKER) as db:
            return await _claim_alert(db, alert_id, user_id, current_value)
    async with AsyncSessionLocal() as db:
        await set_user_background_context(db, user_id)
        return await _claim_alert(db, alert_id, user_id, current_value)


async def check_price_alerts() -> None:
    # Cross-tenant discovery is the only system-scoped part of this job.
    async with trusted_background_session(BackgroundCapability.ALERT_CHECKER) as db:
        from backend.repositories.alerts import get_enabled_alerts

        alerts = list(await get_enabled_alerts(db))

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
        if hit:
            _logger.info(
                "Alert triggered: %s %s $%.2f (current: $%.2f)",
                alert.ticker,
                alert.condition,
                alert.target_price,
                price,
            )
            await _claim_alert_for_owner(alert.id, alert.user_id, float(price))

    indicator_histories = await _fetch_indicator_histories(indicator_alerts) if indicator_alerts else {}
    for alert in indicator_alerts:
        try:
            hit, detail = _evaluate_indicator_alert(alert, indicator_histories.get(alert.ticker))
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Indicator alert check failed for %s: %s", alert.ticker, exc)
            continue
        if hit:
            _logger.info("Indicator alert triggered: %s %s (%s)", alert.ticker, alert.alert_type, detail)
            await _claim_alert_for_owner(alert.id, alert.user_id, None)

    await process_alert_outbox()


async def _throttled_analyze(
    ticker: str,
    trade_date: str,
    user_id: int | None,
    semaphore: asyncio.Semaphore,
) -> None:
    """Acquire *semaphore* before running ``_auto_analyze`` to cap concurrency."""
    async with semaphore:
        await _auto_analyze(ticker, trade_date, user_id)

async def _auto_analyze(ticker: str, trade_date: str, user_id: int | None) -> None:
    try:
        async with AsyncSessionLocal() as new_db:
            if user_id is not None:
                await set_user_background_context(new_db, user_id)
            user = await get_user_by_id(new_db, user_id) if user_id is not None else None
            if not user:
                return
            settings = await get_or_create_settings(new_db, user)
            task_id = str(uuid.uuid4())
            from backend.repositories.analysis import create_analysis_result
            from backend.services.analysis_queue import dispatch_analysis
            from backend.services.analysis_service import register_queued_task

            await create_analysis_result(
                new_db,
                task_id=task_id,
                user_id=user.id,
                ticker=ticker,
                trade_date=trade_date,
                asset_type="stock",
                status="queued",
                heartbeat_at=datetime.now(UTC),
                triggered_by="alert",
            )
            await register_queued_task(
                task_id,
                ticker=ticker,
                trade_date=trade_date,
                asset_type="stock",
                user_id=user.id,
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
    async with trusted_background_session(BackgroundCapability.ALERT_RECOVERY) as db:
        triggered_alerts = await list_triggered_auto_analyze_alerts(db)
        recovery_candidates: list[tuple[str, str, int | None]] = []
        seen_candidates: set[tuple[str, str, int | None]] = set()
        for alert in triggered_alerts:
            trigger_date = alert.triggered_at.strftime("%Y-%m-%d")
            recovery_key = (alert.ticker, trigger_date, alert.user_id)
            if recovery_key not in seen_candidates:
                seen_candidates.add(recovery_key)
                recovery_candidates.append(recovery_key)

        existing_keys = await existing_alert_analysis_keys(db, seen_candidates)
        missing = [key for key in recovery_candidates if key not in existing_keys]
        for ticker, trigger_date, _user_id in missing:
            _logger.warning(
                "Recovering lost alert analysis task for %s (triggered at %s)",
                ticker,
                trigger_date,
            )

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
