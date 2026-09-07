"""AI portfolio rebalancing suggestions.

Every actionable number — action, ticker, quantity, health score, issue list —
is computed deterministically in ``portfolio_rebalance_planner`` from the live
portfolio snapshot. The model is given the finished plan and writes only prose:
a summary and a per-trade rationale.

This is deliberate. The suggestions feed an order form, so a model that could
choose quantities could size a real trade; it also previously returned a health
score unrelated to the issues it listed. The prose is replaceable, the numbers
are not.
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.services.indicator_service import fetch_sector
from backend.services.portfolio_rebalance_planner import build_plan

_logger = logging.getLogger(__name__)

# The plan carries the score, issues and trades; only prose can be missing.
_NO_NARRATIVE: dict = {"summary": "", "rationales": []}
_REBALANCE_SECTOR_CONCURRENCY = 6

async def get_rebalance_suggestions(db: AsyncSession, user: User) -> dict:
    from backend.services.mock_trading_service import get_portfolio_with_live_prices

    portfolio = await get_portfolio_with_live_prices(
        db,
        user=user,
        read_only=True,
        release_before_price_io=True,
    )
    holdings = portfolio.get("holdings") or []

    if not holdings:
        return {
            "summary": "No open positions found. Start trading to receive rebalancing suggestions.",
            "score": 100,
            "issues": [],
            "suggestions": [],
        }

    plan = build_plan(portfolio)
    if not plan["suggestions"] and not plan["issues"]:
        return {
            "summary": "No concentration or cash-allocation issues found.",
            "score": plan["score"],
            "issues": [],
            "suggestions": [],
        }

    tickers = [h["ticker"] for h in holdings]
    # Start sector network I/O immediately, but release the request's DB
    # transaction as soon as the independent signal query completes rather than
    # holding a pool connection until every sector provider call finishes.
    sector_task = asyncio.create_task(_fetch_sectors(tickers))
    try:
        recent_signals = await _get_recent_signals(db, user, tickers)
        await db.commit()
        sectors = await sector_task
    finally:
        if not sector_task.done():
            sector_task.cancel()

    prompt = _build_prompt(portfolio, sectors, recent_signals, plan)
    narrative = await _call_llm(db, user, prompt)
    return _merge(plan, narrative)

async def _fetch_sectors(tickers: list[str]) -> dict[str, str]:
    semaphore = asyncio.Semaphore(_REBALANCE_SECTOR_CONCURRENCY)

    async def _one(ticker: str) -> tuple[str, str]:
        async with semaphore:
            sector = await fetch_sector(ticker)
            return ticker, sector

    pairs = await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=False)
    return dict(pairs)

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

def _build_prompt(portfolio: dict, sectors: dict[str, str], signals: list, plan: dict) -> str:
    """Ask for prose only. Every number below is already decided."""
    total: float = portfolio.get("total_value") or 1.0

    holding_lines = []
    for h in portfolio.get("holdings", []):
        t = h["ticker"]
        weight = (h.get("market_value") or 0) / total * 100
        pnl_pct = h.get("pnl_pct") or 0.0
        sector = sectors.get(t, "Unknown")
        holding_lines.append(
            f"  {t} ({sector}): {weight:.1f}% | "
            f"market value ${h.get('market_value', 0):,.0f} | "
            f"P&L {pnl_pct:+.1f}%"
        )

    signal_lines = [f"  {r.ticker} ({r.trade_date}): {r.signal or 'N/A'}" for r in signals] or [
        "  No recent analyses available."
    ]

    issue_lines = [f"  - {issue}" for issue in plan["issues"]] or ["  - None."]
    trade_lines = [
        f"  {i}. {s['action']} {s['quantity']} {s['ticker']} "
        f"(~${s['notional']:,.0f}; currently {s['weight_pct']:.1f}% of the portfolio)"
        for i, s in enumerate(plan["suggestions"], start=1)
    ] or ["  None required."]

    return f"""You are explaining a portfolio rebalancing plan that has already been calculated.

Portfolio:
- Total Value: ${total:,.2f}
- Cash: {plan['cash_pct']:.1f}%
- Health score: {plan['score']}/100
- Positions:
{chr(10).join(holding_lines)}

Recent AI Signals:
{chr(10).join(signal_lines)}

Detected issues:
{chr(10).join(issue_lines)}

Planned trades:
{chr(10).join(trade_lines)}

Write ONLY a valid JSON object — no markdown, no prose outside it — with this schema:
{{
  "summary": "<2-3 sentences on portfolio health and the main risk>",
  "rationales": ["<one short sentence per planned trade, in the order listed>"]
}}

Rules:
- Do NOT propose trades, quantities, tickers or a score. They are fixed.
- Return exactly {len(plan['suggestions'])} rationale(s), matching the order above.
- Explain why each listed trade helps, referring to the detected issues."""

def _merge(plan: dict, narrative: dict) -> dict:
    """Attach model prose to the computed plan.

    The plan is the source of truth: a missing, short or over-long rationale
    list degrades to an empty string rather than shifting explanations onto the
    wrong trade.
    """
    rationales = narrative.get("rationales")
    if not isinstance(rationales, list):
        rationales = []

    suggestions = []
    for index, trade in enumerate(plan["suggestions"]):
        rationale = rationales[index] if index < len(rationales) else ""
        suggestions.append(
            {
                "action": trade["action"],
                "ticker": trade["ticker"],
                "quantity": trade["quantity"],
                "rationale": str(rationale)[:400],
                "urgency": trade["urgency"],
            }
        )

    summary = str(narrative.get("summary") or "").strip()
    if not summary:
        # Stated from the measurements rather than left blank when the model
        # produced nothing usable.
        issue_count = len(plan["issues"])
        summary = (
            f"Health score {plan['score']}/100 with {issue_count} policy issue(s) "
            f"and {len(plan['suggestions'])} suggested trade(s)."
        )

    return {
        "summary": summary[:1000],
        "score": plan["score"],
        "issues": plan["issues"],
        "suggestions": suggestions,
    }

async def _call_llm(db: AsyncSession, user: User, prompt: str) -> dict:
    from langchain_core.messages import HumanMessage

    from backend.core.config import get_settings
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.services.settings_service import get_or_create_settings
    from backend.services.user_service import get_user_api_key
    from backend.trading_agents.llm_clients.factory import create_llm_client
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    settings = await get_or_create_settings(db, user)
    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm.get("llm_provider") or settings.llm_provider
    model = pm.get("llm_model") or settings.llm_model

    try:
        user_key = get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception as exc:
        _logger.debug("Failed to retrieve user API key: %s", exc)
        user_key = None

    # Settings/runtime reads are complete. Do not pin a pool connection while
    # waiting on the narrative model; the same AsyncSession will reapply its RLS
    # context automatically if a later DB transaction is needed.
    await db.commit()

    if provider_requires_api_key(provider) and not user_key:
        # The plan needs no model, so a missing key costs the explanation only.
        _logger.info("Rebalance narrative skipped: no API key for provider %r", provider)
        return _NO_NARRATIVE

    lang = (settings.output_language or "English").strip()
    if lang.lower() != "english":
        prompt += f"\n- All natural language text fields (summary, issues, rationale) MUST be written in {lang}."

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        from backend.services.llm_content import llm_text
        content = llm_text(response)
    except Exception as e:
        # The plan is already computed and is the part the user acts on, so a
        # model outage costs the explanation, not the suggestions.
        _logger.warning("Rebalance narrative unavailable: %s", e)
        return _NO_NARRATIVE

    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _logger.warning("Could not parse rebalance narrative JSON: %.200s", content)
        return _NO_NARRATIVE

    if not isinstance(parsed, dict):
        return _NO_NARRATIVE
    return {"summary": parsed.get("summary") or "", "rationales": parsed.get("rationales") or []}
