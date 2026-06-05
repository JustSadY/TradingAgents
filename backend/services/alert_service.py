import asyncio
import logging
import uuid
import yfinance as yf
from datetime import datetime, timezone
from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.models.alert import PriceAlert
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.models.analysis import AnalysisResult
from backend.services.notification_service import notify_alert_triggered
from backend.services.analysis_service import run_analysis
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()


async def check_price_alerts() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert).where(PriceAlert.enabled == True, PriceAlert.triggered_at.is_(None))
        )
        alerts = result.scalars().all()
        if not alerts:
            return
        settings_res = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = settings_res.scalar_one_or_none()
        prices = await asyncio.to_thread(_fetch_prices, [a.ticker for a in alerts])
        for alert in alerts:
            price = prices.get(alert.ticker)
            if price is None:
                continue
            hit = (alert.condition == "above" and price >= alert.target_price) or \
                  (alert.condition == "below" and price <= alert.target_price)
            if not hit:
                continue
            alert.triggered_at = datetime.now(timezone.utc)
            _logger.info("Alert triggered: %s %s $%.2f (current: $%.2f)",
                         alert.ticker, alert.condition, alert.target_price, price)
            if settings:
                await notify_alert_triggered(alert.ticker, alert.condition, alert.target_price, settings)
            if alert.auto_analyze:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                task = asyncio.create_task(_auto_analyze(alert.ticker, today, alert.user_id))
                _BACKGROUND_TASKS.add(task)
                task.add_done_callback(_BACKGROUND_TASKS.discard)
        await db.commit()


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    prices = {}
    unique = list(set(tickers))
    try:
        data = yf.download(unique, period="1d", progress=False, auto_adjust=True)
        if "Close" in data.columns:
            close = data["Close"].iloc[-1]
            for t in unique:
                try:
                    prices[t] = float(close[t])
                except Exception:
                    pass
        else:
            for t in unique:
                try:
                    prices[t] = float(yf.Ticker(t).fast_info.last_price or 0)
                except Exception:
                    pass
    except Exception as exc:
        _logger.debug("Batch price fetch failed: %s", exc)
        for t in unique:
            try:
                prices[t] = float(yf.Ticker(t).fast_info.last_price or 0)
            except Exception:
                pass
    return prices


async def _auto_analyze(ticker: str, trade_date: str, user_id: int) -> None:
    try:
        async with AsyncSessionLocal() as new_db:
            result = await new_db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return
            settings = await get_or_create_settings(new_db, user)
            task_id = str(uuid.uuid4())
            await run_analysis(ticker, trade_date, "stock", settings, new_db,
                               triggered_by="alert", task_id=task_id, user=user)
            await new_db.commit()
    except Exception as exc:
        _logger.error("Auto-analyze from alert failed %s: %s", ticker, exc)


async def check_and_recover_lost_alerts() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert)
            .where(PriceAlert.enabled == True)
            .where(PriceAlert.triggered_at.isnot(None))
            .where(PriceAlert.auto_analyze == True)
        )
        triggered_alerts = result.scalars().all()
        for alert in triggered_alerts:
            trigger_date = alert.triggered_at.strftime("%Y-%m-%d")
            res_analysis = await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.ticker == alert.ticker)
                .where(AnalysisResult.trade_date == trigger_date)
                .where(AnalysisResult.user_id == alert.user_id)
                .where(AnalysisResult.triggered_by == "alert")
            )
            analysis = res_analysis.scalar_one_or_none()
            if not analysis:
                _logger.warning("Recovering lost alert analysis task for %s (triggered at %s)", alert.ticker, trigger_date)
                task = asyncio.create_task(_auto_analyze(alert.ticker, trigger_date, alert.user_id))
                _BACKGROUND_TASKS.add(task)
                task.add_done_callback(_BACKGROUND_TASKS.discard)
