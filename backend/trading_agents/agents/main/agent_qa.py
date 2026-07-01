"""Inter-agent cross-examination.

After the analysts finish their reports, this node lets the agents question each
other to resolve conflicts before the research manager synthesizes a plan: a
moderator picks the sharpest cross-agent questions, and each one is answered by
the *target* analyst — using that analyst's own configured LLM and its own
report. The resulting transcript is added to the state and stored in vector
memory so future runs can recall how a similar set of conflicts was reconciled.

The node is a no-op when disabled, when fewer than two analysts produced a
report, or on any error (memory/LLM) — it must never break the pipeline.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext, bind_structured

logger = logging.getLogger(__name__)

MAIN_KEY = "agent_qa"
_MAX_QUESTIONS = 3

_ANALYST_REPORTS: list[tuple[str, str, str]] = [
    ("market", "market_report", "Market Analyst"),
    ("social", "sentiment_report", "Sentiment Analyst"),
    ("news", "news_report", "News Analyst"),
    ("fundamentals", "fundamentals_report", "Fundamentals Analyst"),
    ("macro", "macro_report", "Macro Analyst"),
    ("options", "options_report", "Options Analyst"),
    ("quant", "quant_report", "Quant Analyst"),
    ("earnings", "earnings_report", "Earnings Analyst"),
    ("insider", "insider_report", "Insider Activity Analyst"),
    ("ownership", "ownership_report", "Institutional Ownership Analyst"),
    ("ratings", "ratings_report", "Analyst Ratings Analyst"),
    ("short_interest", "short_interest_report", "Short Interest Analyst"),
    ("valuation", "valuation_report", "Valuation Analyst"),
    ("catalyst", "catalyst_report", "Catalyst Calendar Analyst"),
    ("review", "review_report", "Performance Review Analyst"),
]


class _Question(BaseModel):
    to: str = Field(description="The label of the analyst who should answer (exactly as listed).")
    question: str = Field(description="A focused question that probes a conflict or gap in that analyst's report.")


class _Questions(BaseModel):
    questions: list[_Question] = Field(default_factory=list)


def create_agent_qa_node(ctx: AgentRunContext) -> NodeFn:
    async def agent_qa_node(state) -> dict:
        from backend.trading_agents.dataflows.config import get_config

        if not get_config().get("agent_qa_enabled", True):
            return {}

        available = [
            (key, label, state.get(field) or "")
            for key, field, label in _ANALYST_REPORTS
            if (state.get(field) or "").strip()
        ]
        if len(available) < 2:
            return {}  # nothing to cross-examine

        def _normalize(name: str) -> str:
            return (
                "".join(c for c in name.lower() if c.isalnum()).replace("analyst", "").replace("researcher", "").strip()
            )

        by_normalized = {_normalize(label): (key, label, report) for key, label, report in available}
        moderator = ctx.llm_for(MAIN_KEY)

        try:
            questions = await _generate_questions(moderator, available)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[agent_qa] question generation failed: %s", exc)
            return {}
        if not questions:
            return {}

        async def _process_question(q):
            target = by_normalized.get(_normalize(q.to or ""))
            if not target:
                return None
            target_key, target_label, target_report = target
            try:
                answer = await _answer_as_analyst(ctx, target_key, target_label, target_report, q.question)
                return f"**Q → {target_label}:** {q.question}\n**{target_label}:** {answer}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("[agent_qa] answer by %s failed: %s", q.to, exc)
                return None

        tasks = [_process_question(q) for q in questions[:_MAX_QUESTIONS]]
        results = await asyncio.gather(*tasks)
        transcript_parts = [r for r in results if r is not None]

        if not transcript_parts:
            return {}

        transcript = "### Analyst Cross-Examination\n\n" + "\n\n".join(transcript_parts)

        try:
            from backend.services.memory_service import record_agent_qa

            await record_agent_qa(
                user_id=get_config().get("user_id"),
                ticker=state.get("company_of_interest", ""),
                trade_date=state.get("trade_date", ""),
                situation_text=state.get("market_report", ""),
                transcript=transcript,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[agent_qa] memory store failed (non-fatal): %s", exc)

        return {"agent_qa_report": transcript}

    return agent_qa_node


async def _generate_questions(moderator, available: list[tuple[str, str, str]]) -> list[_Question]:
    """Ask the moderator for up to a few sharp cross-agent questions."""
    from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

    reports_block = "\n\n".join(f"### {label}\n{report.strip()[:2000]}" for _key, label, report in available)
    labels = ", ".join(label for _k, label, _r in available)
    prompt = (
        "You are moderating a panel of equity analysts who have each written a report. "
        "Identify the most important disagreements or unanswered gaps BETWEEN their reports, "
        f"and write up to {_MAX_QUESTIONS} focused questions that one analyst should put to another. "
        f"Each question's 'to' must be exactly one of: {labels}. "
        "Prefer questions that force an analyst to defend a claim another analyst contradicts.\n\n"
        f"{reports_block}" + get_general_settings_block()
    )
    structured = bind_structured(moderator, _Questions, "Q&A Moderator")
    result = await ainvoke_structured_or_freetext(structured, moderator, prompt, "Q&A Moderator", schema=_Questions)
    if isinstance(result, _Questions):
        return result.questions
    return []  # free-text fallback isn't reliably parseable; skip Q&A this run


async def _answer_as_analyst(ctx: AgentRunContext, analyst_key: str, label: str, report: str, question: str) -> str:
    """Answer a peer's question in the target analyst's voice, using its own LLM
    and its own report."""
    from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

    llm = ctx.llm_for(analyst_key)
    messages = [
        (
            "system",
            f"You are the {label}. Answer a peer analyst's question using ONLY your own report and analysis. "
            "Be concise (2-4 sentences), concede points your report cannot support, and do not invent new data."
            + get_general_settings_block(),
        ),
        ("human", f"Your report:\n{report.strip()[:4000]}\n\nPeer's question: {question}"),
    ]
    response = await llm.ainvoke(messages)
    return getattr(response, "content", str(response)).strip()
