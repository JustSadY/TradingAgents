"""AI portfolio rebalancing suggestions.

Fetches the user's current holdings (with live prices), sector data from
yfinance, recent analysis signals, then asks the user's configured LLM to
analyse concentration risk, diversification, and cash allocation — returning
a structured list of suggested BUY/SELL actions with a health score.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

_logger = logging.getLogger(__name__)

_FALLBACK = {
    "summary": "Unable to generate suggestions right now.",
    "score": 50,
    "issues": ["LLM response could not be parsed."],
    "suggestions": [],
}


async def get_rebalance_suggestions(db: AsyncSession, user: User) -> dict:
    from backend.services.mock_trading_service import get_portfolio_with_live_prices

    portfolio = await get_portfolio_with_live_prices(db, user=user)
    holdings = portfolio.get("holdings") or []

    if not holdings:
        return {
            "summary": "No open positions found. Start trading to receive rebalancing suggestions.",
            "score": 100,
            "issues": [],
            "suggestions": [],
        }

    tickers = [h["ticker"] for h in holdings]
    sectors = await _fetch_sectors(tickers)
    recent_signals = await _get_recent_signals(db, user, tickers)

    prompt = _build_prompt(portfolio, sectors, recent_signals)
    return await _call_llm(db, user, prompt)


# ── Sector lookup ─────────────────────────────────────────────────────────────


async def _fetch_sectors(tickers: list[str]) -> dict[str, str]:
    async def _one(ticker: str) -> tuple[str, str]:
        try:
            import yfinance as yf

            info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
            return ticker, info.get("sector") or "Unknown"
        except Exception:
            return ticker, "Unknown"

    pairs = await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=False)
    return dict(pairs)  # type: ignore[arg-type]


# ── Recent signals ────────────────────────────────────────────────────────────


async def _get_recent_signals(db: AsyncSession, user: User, tickers: list[str]) -> list:
    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult
    from backend.repositories.common import scope_to_user

    q = (
        select(AnalysisResult.ticker, AnalysisResult.trade_date, AnalysisResult.signal)
        .where(AnalysisResult.status == "completed")
        .where(AnalysisResult.ticker.in_(tickers))
        .order_by(AnalysisResult.created_at.desc())
        .limit(20)
    )
    q = scope_to_user(q, AnalysisResult, user)
    rows = (await db.execute(q)).fetchall()
    return list(rows)


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(portfolio: dict, sectors: dict[str, str], signals: list) -> str:
    total: float = portfolio.get("total_value") or 1.0
    cash: float = portfolio.get("cash_available") or 0.0
    cash_pct = cash / total * 100

    holding_lines = []
    for h in portfolio.get("holdings", []):
        t = h["ticker"]
        weight = (h.get("market_value") or 0) / total * 100
        pnl_pct = h.get("pnl_pct") or 0.0
        sector = sectors.get(t, "Unknown")
        holding_lines.append(
            f"  {t} ({sector}): {weight:.1f}% | "
            f"market value ${h.get('market_value', 0):,.0f} | "
            f"P&L {pnl_pct:+.1f}% | qty {h.get('quantity', 0):.4f}"
        )

    signal_lines = [f"  {r.ticker} ({r.trade_date}): {r.signal or 'N/A'}" for r in signals] or [
        "  No recent analyses available."
    ]

    return f"""Analyze this paper trading portfolio and provide rebalancing suggestions.

Portfolio:
- Total Value: ${total:,.2f}
- Cash: ${cash:,.2f} ({cash_pct:.1f}%)
- Positions:
{chr(10).join(holding_lines)}

Recent AI Signals:
{chr(10).join(signal_lines)}

Return ONLY a valid JSON object — no markdown, no prose — with this exact schema:
{{
  "summary": "<2-3 sentence overview of health and key risks>",
  "score": <integer 0-100>,
  "issues": ["<issue>", ...],
  "suggestions": [
    {{
      "action": "BUY" | "SELL",
      "ticker": "<symbol>",
      "quantity": <positive number>,
      "rationale": "<why>",
      "urgency": "low" | "medium" | "high"
    }}
  ]
}}

Rules:
- Flag any single position >25% of portfolio as high concentration.
- Healthy cash range: 5-15%. Flag <5% (under-reserved) or >30% (idle).
- Suggest SELL for over-concentrated positions, BUY for diversification.
- Only suggest BUY for tickers the user already owns or well-known stocks.
- Keep suggestions to a maximum of 5.
- Quantities must be realistic given portfolio size."""


# ── LLM call ─────────────────────────────────────────────────────────────────


async def _call_llm(db: AsyncSession, user: User, prompt: str) -> dict:
    from langchain_core.messages import HumanMessage

    from backend.core.config import get_settings
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.services.settings_service import get_or_create_settings
    from backend.services.user_service import get_user_api_key
    from backend.trading_agents.llm_clients.factory import create_llm_client

    settings = await get_or_create_settings(db, user)
    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm.get("llm_provider") or settings.llm_provider
    model = pm.get("llm_model") or settings.llm_model

    try:
        user_key = get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception:
        user_key = None

    if not user_key and not user.is_admin:
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{provider}'. Please add it in Settings.",
        )

    lang = (settings.output_language or "English").strip()
    if lang.lower() != "english":
        prompt += f"\n- All natural language text fields (summary, issues, rationale) MUST be written in {lang}."

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (response.content or "").strip()
    except Exception as e:
        _logger.warning("Rebalance LLM error: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM error: {e}") from e

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(content)
        # Basic validation
        result.setdefault("summary", "")
        result.setdefault("score", 70)
        result.setdefault("issues", [])
        result.setdefault("suggestions", [])
        return result
    except json.JSONDecodeError:
        _logger.warning("Could not parse rebalance JSON: %.200s", content)
        return {**_FALLBACK, "summary": content[:400]}
