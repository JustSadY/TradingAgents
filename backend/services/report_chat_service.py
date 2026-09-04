"""Interactive Q&A over a completed analysis report.

Encapsulates the report-grounded chat that used to live inline in the
``/analysis/{id}/chat`` route handler: ownership checks, report context
assembly, LLM client construction, conversation history, and persistence.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.models import AnalysisChat
from backend.models.analysis import AnalysisResult
from backend.services.llm_content import llm_text
from backend.services.settings_service import get_or_create_settings
from backend.services.user_service import resolve_user_api_key

_logger = logging.getLogger(__name__)

_REPORT_SECTIONS = [
    ("MARKET REPORT", "market_report"),
    ("SENTIMENT REPORT", "sentiment_report"),
    ("NEWS REPORT", "news_report"),
    ("FUNDAMENTALS REPORT", "fundamentals_report"),
    ("MACRO REPORT", "macro_report"),
    ("OPTIONS REPORT", "options_report"),
    ("QUANT REPORT", "quant_report"),
    ("EARNINGS REPORT", "earnings_report"),
    ("INSIDER ACTIVITY REPORT", "insider_report"),
    ("INSTITUTIONAL OWNERSHIP REPORT", "ownership_report"),
    ("ANALYST RATINGS REPORT", "ratings_report"),
    ("SHORT INTEREST REPORT", "short_interest_report"),
    ("VALUATION COMPARISON REPORT", "valuation_report"),
    ("UPCOMING CATALYSTS REPORT", "catalyst_report"),
]

_MAX_SECTION_CHARS = 5000
_MAX_PROMPT_HISTORY_MESSAGES = 20
_REPORT_COLUMNS = tuple(getattr(AnalysisResult, attr) for _, attr in _REPORT_SECTIONS)


def _capped(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_SECTION_CHARS:
        return text
    return text[:_MAX_SECTION_CHARS].rstrip() + "\n…[section truncated to conserve tokens]"


async def _get_owned_analysis(db: AsyncSession, analysis_id: int, user) -> AnalysisResult:
    # Report chat does not need strategy snapshots, debate histories, raw JSON,
    # token accounting, or other large AnalysisResult fields. Loading only the
    # report surface keeps one chat turn from pulling the full analysis row.
    q = (
        select(AnalysisResult)
        .where(AnalysisResult.id == analysis_id)
        .options(
            load_only(
                AnalysisResult.id,
                AnalysisResult.ticker,
                AnalysisResult.signal,
                AnalysisResult.final_decision,
                *_REPORT_COLUMNS,
            )
        )
    )
    if user is not None and not getattr(user, "is_admin", False):
        q = q.where(AnalysisResult.user_id == user.id)
    analysis = (await db.execute(q)).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    return analysis


async def _list_chat_history(db: AsyncSession, analysis_id: int) -> list[AnalysisChat]:
    result = await db.execute(
        select(AnalysisChat).where(AnalysisChat.analysis_id == analysis_id).order_by(AnalysisChat.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_prompt_history(db: AsyncSession, analysis_id: int) -> list[AnalysisChat]:
    """Return only the newest bounded chat window, restored to chronological order."""
    result = await db.execute(
        select(AnalysisChat)
        .where(AnalysisChat.analysis_id == analysis_id)
        .order_by(AnalysisChat.created_at.desc())
        .limit(_MAX_PROMPT_HISTORY_MESSAGES)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def get_chat_history(db: AsyncSession, analysis_id: int, user) -> list[AnalysisChat]:
    await _get_owned_analysis(db, analysis_id, user)
    return await _list_chat_history(db, analysis_id)


def _build_report_context(analysis: AnalysisResult) -> str:
    parts = [
        f"### {heading}\n{_capped(getattr(analysis, attr))}"
        for heading, attr in _REPORT_SECTIONS
        if getattr(analysis, attr, None)
    ]
    if analysis.final_decision:
        parts.append(f"### FINAL PORTFOLIO DECISION & SIGNAL ({analysis.signal})\n{analysis.final_decision}")
    return "\n\n".join(parts)


def _build_system_prompt(analysis: AnalysisResult, output_language: str | None) -> str:
    lang = (output_language or "English").strip()
    lang_inst = "" if lang.lower() == "english" else f" Write your entire response in {lang}."
    return (
        "You are the Portfolio Manager agent of the TradingAgents platform. The user wants to "
        f"discuss the following completed analysis report for asset `{analysis.ticker}`.\n\n"
        "--- START REPORT CONTENT ---\n"
        f"{_build_report_context(analysis)}\n"
        "--- END REPORT CONTENT ---\n\n"
        "Answer the user's questions about this analysis report accurately, professionally, and "
        "concisely. Ground your replies only in the details provided in the report. If they ask "
        f"about something not covered in the report, say so politely.{lang_inst}"
    )


async def answer_report_question(
    db: AsyncSession,
    analysis_id: int,
    message: str,
    user,
) -> AnalysisChat:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from backend.trading_agents.llm_clients.factory import create_llm_client

    analysis = await _get_owned_analysis(db, analysis_id, user)
    settings = await get_or_create_settings(db, user)

    # Ownership was already verified above. Do not issue the same analysis
    # lookup again merely to load the prompt's conversation window.
    past_messages = await _list_prompt_history(db, analysis_id)
    payload = [SystemMessage(content=_build_system_prompt(analysis, settings.output_language))]
    for msg in past_messages:
        payload.append(HumanMessage(content=msg.content) if msg.role == "user" else AIMessage(content=msg.content))
    payload.append(HumanMessage(content=message))

    from backend.services.agent_settings_service import build_agent_runtime_context

    agent_ctx = await build_agent_runtime_context(db, user.id if user else None)
    pm_settings = agent_ctx.get("portfolio_manager", {}).get("settings", {})

    active_provider = pm_settings.get("llm_provider") or settings.llm_provider
    active_model = pm_settings.get("llm_model") or settings.llm_model

    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    user_key = resolve_user_api_key(user, active_provider)
    if provider_requires_api_key(active_provider) and not user_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{active_provider}'. Please add your API key in Settings.",
        )

    client = create_llm_client(
        provider=active_provider,
        model=active_model,
        api_key=user_key,
    )

    try:
        llm = client.get_llm()
        response = await llm.ainvoke(payload)
    except ValueError as exc:
        _logger.warning("Report chat model request rejected: %s", exc)
        raise HTTPException(status_code=400, detail="The model request or configuration is invalid") from exc

    db.add(AnalysisChat(analysis_id=analysis_id, role="user", content=message))
    assistant_chat = AnalysisChat(analysis_id=analysis_id, role="assistant", content=llm_text(response))
    db.add(assistant_chat)
    await db.flush()
    return assistant_chat
