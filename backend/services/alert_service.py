import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.models.alert import PriceAlert
from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.services.analysis_service import run_analysis
from backend.services.market_data_service import get_live_prices_batch
from backend.services.notification_service import notify_alert_triggered
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# Concurrency limits
_RECOVERY_SEMAPHORE = asyncio.Semaphore(3)
_ALERT_SEMAPHORE = asyncio.Semaphore(5)

_INDICATOR_ALERT_TYPES = frozenset({"rsi", "macd_cross"})


async def _fetch_alert_market_summary(ticker: str) -> str:
    try:
        import yfinance as yf

        info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
        hist = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="5d"))

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


async def _notify_and_maybe_analyze(db, alert: PriceAlert, settings, current_value: float | None) -> None:
    """Shared trigger side-effects: mark triggered, notify, optionally auto-analyze."""
    alert.triggered_at = datetime.now(UTC)

    summary = await _fetch_alert_market_summary(alert.ticker)
    if summary:
        _logger.info("Alert market summary for %s: %s", alert.ticker, summary)

    if settings:
        user = await db.get(User, alert.user_id)
        user_settings = await get_or_create_settings(db, user)
        await notify_alert_triggered(
            alert.ticker,
            alert.condition,
            current_value if current_value is not None else float(alert.target_price),
            user_settings,
            alert_type=getattr(alert, "alert_type", "price"),
            market_summary=summary,
        )

    if alert.auto_analyze:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        task = asyncio.create_task(_throttled_analyze(alert.ticker, today, alert.user_id, _ALERT_SEMAPHORE))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)


async def check_price_alerts() -> None:
    async with AsyncSessionLocal() as db:
        from backend.repositories.alerts import get_enabled_alerts

        alerts = await get_enabled_alerts(db)
        if not alerts:
            return

        from backend.repositories.system_settings import get_system_settings

        settings = await get_system_settings(db)

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
            await _notify_and_maybe_analyze(db, alert, settings, float(price))

        for alert in indicator_alerts:
            try:
                hit, detail = await _check_indicator_alert(alert)
            except Exception as exc:  # noqa: BLE001 — one bad ticker must not break the loop
                _logger.warning("Indicator alert check failed for %s: %s", alert.ticker, exc)
                continue
            if not hit:
                continue

            _logger.info("Indicator alert triggered: %s %s (%s)", alert.ticker, alert.alert_type, detail)
            await _notify_and_maybe_analyze(db, alert, settings, None)

        await db.commit()


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
            await run_analysis(
                ticker, trade_date, "stock", settings, new_db, triggered_by="alert", task_id=task_id, user=user
            )
            await new_db.commit()
    except Exception:
        _logger.exception("Auto-analyze from alert failed %s", ticker)


async def check_and_recover_lost_alerts() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert)
            .where(PriceAlert.enabled.is_(True))
            .where(PriceAlert.triggered_at.isnot(None))
            .where(PriceAlert.auto_analyze.is_(True))
        )
        triggered_alerts = result.scalars().all()
        # A user can legitimately have more than one alert-driven analysis for
        # the same ticker and date (for example after a retry).  Recovery only
        # needs to know whether *any* such analysis was recorded, so do not use
        # ``scalar_one_or_none()`` on the full result set here.
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
                # Multiple alert rows can describe the same recovery target.
                # Starting each one would duplicate LLM work on server boot.
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
