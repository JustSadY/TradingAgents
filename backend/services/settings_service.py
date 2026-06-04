"""Business logic for per-user application settings (``AppSettings``).

This module owns everything that used to live inside ``api/settings.py`` as
private helpers and was imported across the API and even from other services
(creating an ``api -> service`` dependency inversion). Routers and services now
depend on this service instead.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.schemas.settings import SettingsRead, SettingsUpdate


async def get_or_create_settings(
    db: AsyncSession, user=None,
) -> AppSettings:
    """Return the settings row for ``user`` (or the global row), creating it lazily."""
    user_id = getattr(user, "id", None) if user is not None else None
    if user_id is not None:
        result = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=user_id)
            db.add(settings)
            await db.flush()
        return settings
    result = await db.execute(select(AppSettings).where(AppSettings.user_id.is_(None)).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings()
        db.add(settings)
        await db.flush()
    return settings


def settings_to_read(settings: AppSettings) -> SettingsRead:
    """Map an ``AppSettings`` row to its read DTO (single source of truth)."""
    return SettingsRead(
        trading_mode=settings.trading_mode,
        active_broker=settings.active_broker,
        active_data_vendor=settings.active_data_vendor,
        cron_enabled=settings.cron_enabled,
        cron_schedule=settings.cron_schedule,
        price_tolerance_pct=settings.price_tolerance_pct,
        watchlist=settings.watchlist,
        selected_analysts=settings.selected_analysts,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model or "gpt-4o-mini",
        backend_url=settings.backend_url,
        openai_reasoning_effort=settings.openai_reasoning_effort,
        anthropic_effort=settings.anthropic_effort,
        google_thinking_level=settings.google_thinking_level,
        output_language=settings.output_language or "English",
        investor_persona=settings.investor_persona or "conservative",
        analyst_concurrency_limit=settings.analyst_concurrency_limit or 1,
        checkpoint_enabled=getattr(settings, "checkpoint_enabled", False) or False,
        max_recur_limit=getattr(settings, "max_recur_limit", 1000) or 1000,
        benchmark_ticker=getattr(settings, "benchmark_ticker", None),
        azure_deployment=getattr(settings, "azure_deployment", None),
        data_vendor_core_stock=getattr(settings, "data_vendor_core_stock", None) or "yfinance",
        data_vendor_technicals=getattr(settings, "data_vendor_technicals", None) or "yfinance",
        data_vendor_fundamentals=getattr(settings, "data_vendor_fundamentals", None) or "yfinance",
        data_vendor_news=getattr(settings, "data_vendor_news", None) or "yfinance",
        max_debate_rounds=settings.max_debate_rounds,
        max_risk_rounds=settings.max_risk_rounds,
        max_position_size_pct=settings.max_position_size_pct,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        include_historical_analyses=getattr(settings, "include_historical_analyses", False) or False,
        historical_analyses_limit=getattr(settings, "historical_analyses_limit", 5) or 5,
        analyst_models=getattr(settings, "analyst_models", {}) or {},
        webhook_url=getattr(settings, "webhook_url", None),
        webhook_enabled=getattr(settings, "webhook_enabled", False) or False,
        webhook_events=getattr(settings, "webhook_events", None) or "analysis_complete",
        updated_at=settings.updated_at,
    )


async def apply_settings_update(
    db: AsyncSession, settings: AppSettings, body: SettingsUpdate,
) -> AppSettings:
    """Apply a partial settings update, reset the active preset on real changes,
    persist, and re-sync the user's cron job."""
    has_changes = False
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "active_preset_name":
            settings.active_preset_name = value
            continue
        if getattr(settings, field, None) != value:
            has_changes = True
        setattr(settings, field, value)
    if has_changes:
        # An explicit edit detaches the row from any named preset.
        settings.active_preset_name = None
    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await _resync_cron(settings)
    return settings


async def _resync_cron(settings: AppSettings) -> None:
    from backend.services.cron_service import get_cron_service
    cron = get_cron_service()
    if cron:
        await cron.apply_user_settings(settings)
