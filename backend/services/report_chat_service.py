"""Interactive Q&A over a completed analysis report.

Encapsulates the report-grounded chat that used to live inline in the
``/analysis/{id}/chat`` route handler: ownership checks, report context
assembly, LLM client construction, conversation history, and persistence.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AnalysisChat
from backend.models.analysis import AnalysisResult
from backend.services.settings_service import get_or_create_settings
from backend.services.user_service import get_user_api_key

_logger = logging.getLogger(__name__)

# (heading, attribute) pairs assembled into the LLM's grounding context.
_REPORT_SECTIONS = [
    ("MARKET REPORT", "market_report"),
    ("SENTIMENT REPORT", "sentiment_report"),
    ("NEWS REPORT", "news_report"),
    ("FUNDAMENTALS REPORT", "fundamentals_report"),
    ("MACRO REPORT", "macro_report"),
    ("OPTIONS REPORT", "options_report"),
    ("QUANT REPORT", "quant_report"),
    ("EARNINGS REPORT", "earnings_report"),
]


async def _get_owned_analysis(db: AsyncSession, analysis_id: int, user) -> AnalysisResult:
    q = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
    if user is not None and not getattr(user, "is_admin", False):
        q = q.where(AnalysisResult.user_id == user.id)
    analysis = (await db.execute(q)).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    return analysis


async def get_chat_history(db: AsyncSession, analysis_id: int, user) -> list[AnalysisChat]:
    await _get_owned_analysis(db, analysis_id, user)
    result = await db.execute(
        select(AnalysisChat)
        .where(AnalysisChat.analysis_id == analysis_id)
        .order_by(AnalysisChat.created_at.asc())
    )
    return list(result.scalars().all())


def _build_report_context(analysis: AnalysisResult) -> str:
    parts = [
        f"### {heading}\n{getattr(analysis, attr)}"
        for heading, attr in _REPORT_SECTIONS
        if getattr(analysis, attr, None)
    ]
    if analysis.final_decision:
        parts.append(
            f"### FINAL PORTFOLIO DECISION & SIGNAL ({analysis.signal})\n{analysis.final_decision}"
        )
    return "\n\n".join(parts)


def _build_system_prompt(analysis: AnalysisResult, output_language: Optional[str]) -> str:
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


def _resolve_user_api_key(user, provider: str) -> Optional[str]:
    if user is None:
        return None
    try:
        from backend.core.config import get_settings
        return get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception:
        return None


async def answer_report_question(
    db: AsyncSession, analysis_id: int, message: str, user,
) -> AnalysisChat:
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from backend.trading_agents.llm_clients.factory import create_llm_client

    analysis = await _get_owned_analysis(db, analysis_id, user)
    settings = await get_or_create_settings(db, user)

    past_messages = await get_chat_history(db, analysis_id, user)
    payload = [SystemMessage(content=_build_system_prompt(analysis, settings.output_language))]
    for msg in past_messages:
        payload.append(
            HumanMessage(content=msg.content) if msg.role == "user"
            else AIMessage(content=msg.content)
        )
    payload.append(HumanMessage(content=message))

    user_key = _resolve_user_api_key(user, settings.llm_provider)
    if not user_key and not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{settings.llm_provider}'. "
                   "Please add your API key in Settings.",
        )

    kwargs = {}
    if settings.llm_provider.lower() == "azure" and settings.azure_deployment:
        kwargs["azure_deployment"] = settings.azure_deployment

    client = create_llm_client(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.backend_url,
        api_key=user_key,
        **kwargs,
    )
    response = await client.get_llm().ainvoke(payload)

    db.add(AnalysisChat(analysis_id=analysis_id, role="user", content=message))
    assistant_chat = AnalysisChat(analysis_id=analysis_id, role="assistant", content=response.content)
    db.add(assistant_chat)
    await db.flush()
    return assistant_chat
