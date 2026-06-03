from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.settings import SettingsRead, SettingsUpdate
from backend.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm-catalog")
async def get_llm_catalog(_: User = Depends(get_current_user)):
    """Return all providers and their available models from the model catalog."""
    from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
    catalog = {}
    for provider, modes in MODEL_OPTIONS.items():
        catalog[provider] = {
            mode: [{"label": label, "value": value} for label, value in opts]
            for mode, opts in modes.items()
        }
    return catalog


async def _get_or_create_settings(db: AsyncSession, current_user: User | None = None) -> AppSettings:
    if current_user is not None:
        result = await db.execute(
            select(AppSettings).where(AppSettings.user_id == current_user.id)
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=current_user.id)
            db.add(settings)
            await db.flush()
        return settings
    # Fallback: legacy single-row (id=1) for internal callers without user context
    result = await db.execute(select(AppSettings).where(AppSettings.user_id.is_(None)).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings()
        db.add(settings)
        await db.flush()
    return settings


@router.get("", response_model=SettingsRead)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await _get_or_create_settings(db, _)
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
        news_article_limit=getattr(settings, "news_article_limit", 20) or 20,
        global_news_article_limit=getattr(settings, "global_news_article_limit", 10) or 10,
        global_news_lookback_days=getattr(settings, "global_news_lookback_days", 7) or 7,
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


@router.put("", response_model=SettingsRead)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await _get_or_create_settings(db, _)

    # Validate settings section permissions for non-admin users
    if not _.is_admin:
        from backend.models.page_permission import UserSettingPermission, SECTION_FIELDS
        from fastapi import status
        
        # Fetch the user's enabled settings sections
        result = await db.execute(
            select(UserSettingPermission)
            .where(UserSettingPermission.user_id == _.id)
            .where(UserSettingPermission.allowed == True)
        )
        allowed_sections = {p.setting_key for p in result.scalars().all()}
        
        # Check which fields are modified in this request
        attempted_updates = body.model_dump(exclude_unset=True)
        
        for section, fields in SECTION_FIELDS.items():
            if any(f in attempted_updates for f in fields):
                if section not in allowed_sections:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have permission to modify settings in section: {section}"
                    )
        
        # Protect advanced admin-only settings fields
        advanced_fields = [
            "checkpoint_enabled", "include_historical_analyses", "historical_analyses_limit",
            "news_article_limit", "global_news_article_limit", "global_news_lookback_days",
            "max_recur_limit", "azure_deployment", "data_vendor_core_stock",
            "data_vendor_technicals", "data_vendor_fundamentals", "data_vendor_news"
        ]
        if any(f in attempted_updates for f in advanced_fields):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Advanced engine settings can only be modified by administrators."
            )

    has_changes = False
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "active_preset_name":
            settings.active_preset_name = value
            continue
        if getattr(settings, field, None) != value:
            has_changes = True
        if field == "watchlist":
            settings.watchlist = value
        elif field == "selected_analysts":
            settings.selected_analysts = value
        else:
            setattr(settings, field, value)

    if has_changes:
        settings.active_preset_name = None

    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Notify cron service to reconfigure this user's job
    from backend.services.cron_service import get_cron_service
    cron = get_cron_service()
    if cron:
        await cron.apply_user_settings(settings)

    return await get_settings(db=db, _=_)


class WebhookTestRequest(BaseModel):
    url: str


@router.post("/test-webhook")
async def test_webhook(body: WebhookTestRequest, _: User = Depends(get_current_user)):
    """Send a test notification to the given webhook URL."""
    import httpx
    payload = {"text": "TradingAgents webhook testi başarılı! ✓", "content": "TradingAgents webhook testi başarılı! ✓"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(body.url, json=payload)
            if r.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"Webhook yanıtı: {r.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.get("/users/{user_id}", response_model=SettingsRead)
async def get_user_settings_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Retrieve AppSettings for a specific user. (Admin Only)"""
    from backend.models.user import User
    res = await db.execute(select(User).where(User.id == user_id))
    target_user = res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    settings = await _get_or_create_settings(db, target_user)
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
        news_article_limit=getattr(settings, "news_article_limit", 20) or 20,
        global_news_article_limit=getattr(settings, "global_news_article_limit", 10) or 10,
        global_news_lookback_days=getattr(settings, "global_news_lookback_days", 7) or 7,
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


@router.put("/users/{user_id}", response_model=SettingsRead)
async def update_user_settings_by_id(
    user_id: int,
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update AppSettings for a specific user. (Admin Only)"""
    from backend.models.user import User
    res = await db.execute(select(User).where(User.id == user_id))
    target_user = res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    settings = await _get_or_create_settings(db, target_user)
    
    has_changes = False
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "active_preset_name":
            settings.active_preset_name = value
            continue
        if getattr(settings, field, None) != value:
            has_changes = True
        if field == "watchlist":
            settings.watchlist = value
        elif field == "selected_analysts":
            settings.selected_analysts = value
        else:
            setattr(settings, field, value)

    if has_changes:
        settings.active_preset_name = None

    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Reconfigure user cron schedule if user cron settings updated
    from backend.services.cron_service import get_cron_service
    cron = get_cron_service()
    if cron:
        await cron.apply_user_settings(settings)

    return await get_user_settings_by_id(user_id=user_id, db=db, admin=admin)
