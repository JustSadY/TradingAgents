"""Generate a daily AI market brief for the user's watchlist + sector context."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.market_summary import MarketDailySummary
from backend.models.user import User
from backend.services.settings_service import get_or_create_settings
from backend.services.user_service import resolve_user_api_key

_logger = logging.getLogger(__name__)

async def get_latest_summary(db: AsyncSession, user_id: int) -> dict | None:
    result = await db.execute(
        select(MarketDailySummary)
        .where(MarketDailySummary.user_id == user_id)
        .order_by(MarketDailySummary.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "id": row.id,
        "date": row.date,
        "summary": row.summary,
        "tickers": row.tickers.split(",") if row.tickers else [],
        "generated_at": row.created_at.isoformat() if row.created_at else None,
    }

async def generate_daily_summary(db: AsyncSession, user: User) -> dict:
    today = date.today().isoformat()
    settings = await get_or_create_settings(db, user)
    watchlist: list[str] = list(settings.watchlist or [])[:10]

    from langchain_core.messages import HumanMessage

    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.llm_clients.factory import create_llm_client
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    # Resolve every DB-backed runtime input before starting market-data or LLM
    # network I/O. That lets the request return its database connection to the
    # pool for the potentially slow external phase.
    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm.get("llm_provider") or settings.llm_provider
    model = pm.get("llm_model") or settings.llm_model

    user_key = resolve_user_api_key(user, provider)
    if provider_requires_api_key(provider) and not user_key:
        raise ValueError(f"No API key configured for provider '{provider}'. Add it in Settings.")

    await db.commit()

    price_lines, sector_lines = await asyncio.gather(
        _fetch_watchlist_prices(watchlist),
        _fetch_sector_data(),
    )

    watchlist_block = "\n".join(price_lines) if price_lines else "  (watchlist empty)"
    sector_block = "\n".join(sector_lines) if sector_lines else "  (sector data unavailable)"
    prompt = (
        f"Today is {today}. You are a professional equity analyst writing a morning market brief.\n\n"
        f"Watchlist performance:\n{watchlist_block}\n\n"
        f"Sector rotation (weekly):\n{sector_block}\n\n"
        "Write a concise 4-6 sentence morning market summary for an active investor. Cover: "
        "(1) overall market tone from sector data, "
        "(2) notable watchlist movers, "
        "(3) one key risk or opportunity to watch today. "
        "Use a direct, professional tone. No disclaimers, no markdown headers."
    )

    client = create_llm_client(provider=provider, model=model, api_key=user_key)
    llm = client.get_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    from backend.services.llm_content import llm_text
    summary_text = llm_text(response)
    if not summary_text:
        raise ValueError("The model returned an empty daily summary")

    record = MarketDailySummary(
        user_id=user.id,
        date=today,
        summary=summary_text,
        tickers=",".join(watchlist),
    )
    db.add(record)
    await db.commit()
    # AsyncSessionLocal uses expire_on_commit=False. ``id`` is populated by the
    # INSERT and ``created_at`` also has a Python default, so a post-commit
    # refresh only adds a redundant SELECT.

    return {
        "id": record.id,
        "date": record.date,
        "summary": record.summary,
        "tickers": watchlist,
        "generated_at": record.created_at.isoformat() if record.created_at else None,
    }

async def _fetch_watchlist_prices(watchlist: list[str]) -> list[str]:
    """Helper to fetch and format watchlist prices."""
    price_lines: list[str] = []
    if not watchlist:
        return price_lines

    import pandas as pd
    import yfinance as yf

    loop = asyncio.get_running_loop()

    def _fetch():
        try:
            return yf.download(watchlist, period="2d", progress=False, auto_adjust=True)
        except Exception as exc:
            _logger.warning("yfinance download failed in daily summary: %s", exc)
            return None

    try:
        raw = await loop.run_in_executor(None, _fetch)
        if raw is None or raw.empty:
            return price_lines

        closes = raw["Close"]
        for ticker in watchlist:
            try:
                if isinstance(closes, pd.Series):
                    series = closes.dropna()
                else:
                    series = closes[ticker].dropna()

                if len(series) >= 2:
                    prev, curr = float(series.iloc[-2]), float(series.iloc[-1])
                    chg = (curr - prev) / prev * 100
                    price_lines.append(f"  {ticker}: ${curr:.2f} ({chg:+.1f}%)")
                elif len(series) == 1:
                    price_lines.append(f"  {ticker}: ${float(series.iloc[-1]):.2f}")
            except Exception as exc:
                _logger.debug("Failed to parse prices for ticker %s in daily summary: %s", ticker, exc)
                continue
    except Exception as e:
        _logger.warning("Price fetch failed for daily summary: %s", e)
    return price_lines

async def _fetch_sector_data() -> list[str]:
    """Helper to fetch and format sector rotation data."""
    sector_lines: list[str] = []
    try:
        from backend.services.sector_rotation_service import get_sector_rotation

        sectors = await get_sector_rotation()
        if sectors:
            leaders = sectors[:3]
            laggards = sectors[-3:]

            def _fmt(s: dict) -> str:
                chg = s.get("ret_1w", 0.0)
                return f"{s.get('name', 'N/A')} ({'+' if chg >= 0 else ''}{chg:.1f}% 1W)"

            sector_lines.append(f"  Leaders: {', '.join(_fmt(s) for s in leaders)}")
            sector_lines.append(f"  Laggards: {', '.join(_fmt(s) for s in laggards)}")
    except Exception as e:
        _logger.warning("Sector fetch failed for daily summary: %s", e)
    return sector_lines
