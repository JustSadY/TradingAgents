"""Episodic trading memory (vector-backed).

Replaces the old SQL recency retrieval: instead of "the N most recent same-ticker
analyses", an analysis is stored once its outcome is known (a *situation* embedded
with its decision, realized alpha and the reflection/lesson), and future runs
recall the most *similar* past situations — weighting losses — so the engine can
avoid repeating an action that previously led to a drawdown.

Memory is off (these become no-ops returning "") when no store is configured.
"""

from __future__ import annotations

import logging

from backend.core.memory import MemoryRecord, MemoryStore, build_pinecone_store

_logger = logging.getLogger(__name__)

# Cache built stores by their resolved config so we don't rebuild a Pinecone
# client on every record/recall. Keyed by the full config tuple, so a user
# changing their settings transparently gets a new store.
_store_cache: dict[tuple, MemoryStore | None] = {}


async def get_user_memory_store(user_id: int | None) -> MemoryStore | None:
    """Build the calling user's own memory store from their settings + encrypted
    keys. Returns None (memory off) when the user hasn't configured Pinecone.

    Everything is per-user: the Pinecone API key (provider "pinecone"), the
    index/region/embedder choice (AppSettings), and the OpenAI key (provider
    "openai") when the OpenAI embedder is selected.
    """
    if not user_id:
        return None
    try:
        from sqlalchemy import select

        from backend.core.config import get_settings
        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import AppSettings
        from backend.models.user import User
        from backend.services.user_service import get_user_api_key

        fernet = get_settings().get_fernet()
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if not user:
                return None
            pinecone_key = get_user_api_key(user, "pinecone", fernet)
            if not pinecone_key:
                return None  # this user hasn't enabled memory

            row = (await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))).scalar_one_or_none()
            index = getattr(row, "pinecone_index", None) or "tradingagents-memory"
            cloud = getattr(row, "pinecone_cloud", None) or "aws"
            region = getattr(row, "pinecone_region", None) or "us-east-1"
            embedder_kind = getattr(row, "memory_embedder", None) or "pinecone"
            embed_model = getattr(row, "pinecone_embed_model", None) or "llama-text-embed-v2"
            openai_embed_model = getattr(row, "memory_openai_embed_model", None) or "text-embedding-3-small"
            openai_key = get_user_api_key(user, "openai", fernet) if embedder_kind == "openai" else None
            if embedder_kind == "openai" and not openai_key:
                return None
    except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
        _logger.warning("Could not resolve memory store for user_id=%s: %s", user_id, exc)
        return None

    cache_key = (index, cloud, region, embedder_kind, embed_model, openai_embed_model, pinecone_key, openai_key)
    if cache_key not in _store_cache:
        _store_cache[cache_key] = build_pinecone_store(
            api_key=pinecone_key,
            index_name=index,
            cloud=cloud,
            region=region,
            embedder_kind=embedder_kind,
            embed_model=embed_model,
            openai_api_key=openai_key,
            openai_embed_model=openai_embed_model,
        )
    return _store_cache[cache_key]

# Episodes are isolated per owner so one user's trading history never leaks into
# another's recall.
_SYSTEM_OWNER = "system"
_SITUATION_MAX_CHARS = 4000


def _namespace(user_id: int | None) -> str:
    return f"ep_user_{user_id}" if user_id else f"ep_{_SYSTEM_OWNER}"


def _episode_id(user_id: int | None, ticker: str, trade_date: str) -> str:
    owner = user_id if user_id else _SYSTEM_OWNER
    return f"{owner}:{ticker}:{trade_date}"


async def record_episode(
    *,
    user_id: int | None,
    ticker: str,
    trade_date: str,
    signal: str | None,
    situation_text: str,
    decision: str,
    raw_return: float | None,
    alpha_return: float | None,
    reflection: str,
    store: MemoryStore | None = None,
) -> bool:
    """Store one completed, outcome-known analysis as an episode. Returns True if
    written, False if memory is disabled. Best-effort: never raises."""
    store = store or await get_user_memory_store(user_id)
    if store is None:
        return False

    outcome = "loss" if (alpha_return is not None and alpha_return < 0) else "gain"
    # The embedded text is the *situation* plus its lesson, so recall matches on
    # market context and surfaces the outcome/lesson together.
    text = (situation_text or decision or "")[:_SITUATION_MAX_CHARS]
    if reflection:
        text = f"{text}\n\nLesson: {reflection}"

    record = MemoryRecord(
        id=_episode_id(user_id, ticker, trade_date),
        text=text,
        metadata={
            "ticker": ticker,
            "trade_date": trade_date,
            "signal": signal or "",
            "decision": (decision or "")[:1500],
            "reflection": reflection or "",
            "raw_return": float(raw_return) if raw_return is not None else 0.0,
            "alpha_return": float(alpha_return) if alpha_return is not None else 0.0,
            "outcome": outcome,
        },
    )
    try:
        await store.upsert(_namespace(user_id), [record])
        return True
    except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
        _logger.warning("record_episode failed for %s %s: %s", ticker, trade_date, exc)
        return False


async def recall_episode_lessons(
    *,
    user_id: int | None,
    situation_text: str,
    top_k: int = 5,
    store: MemoryStore | None = None,
) -> str:
    """Return a formatted block of the most similar past episodes for injection
    into a decision prompt, or "" if memory is disabled / nothing relevant.

    Losses are listed first under an explicit "avoid repeating" header so the
    model gives them weight."""
    store = store or await get_user_memory_store(user_id)
    if store is None or not situation_text.strip():
        return ""

    hits = await store.query(_namespace(user_id), situation_text, top_k=top_k)
    if not hits:
        return ""

    losses = [h for h in hits if h.metadata.get("outcome") == "loss"]
    gains = [h for h in hits if h.metadata.get("outcome") != "loss"]

    parts: list[str] = ["### Memory: similar past situations"]

    if losses:
        parts.append("\n**Actions that previously led to a loss — do NOT repeat the same mistake:**")
        for h in losses:
            parts.append(_format_hit(h))
    if gains:
        parts.append("\n**Actions that previously worked out:**")
        for h in gains:
            parts.append(_format_hit(h))

    return "\n".join(parts)


def _format_hit(h) -> str:
    m = h.metadata
    alpha = m.get("alpha_return", 0.0)
    header = (
        f"- {m.get('ticker', '?')} on {m.get('trade_date', '?')} "
        f"({m.get('signal') or 'N/A'}, alpha {float(alpha):+.1%}, similarity {h.score:.2f})"
    )
    reflection = m.get("reflection")
    return f"{header}\n  {reflection}" if reflection else header


# ---------------------------------------------------------------------------
# Inter-agent Q&A memory: cross-examination transcripts so future runs can see
# how analysts reconciled a similar set of conflicting reports.
# ---------------------------------------------------------------------------
_QA_MAX_CHARS = 6000


def _qa_namespace(user_id: int | None) -> str:
    return f"qa_user_{user_id}" if user_id else f"qa_{_SYSTEM_OWNER}"


async def record_agent_qa(
    *,
    user_id: int | None,
    ticker: str,
    trade_date: str,
    situation_text: str,
    transcript: str,
    store: MemoryStore | None = None,
) -> bool:
    store = store or await get_user_memory_store(user_id)
    if store is None or not transcript.strip():
        return False
    record = MemoryRecord(
        id=_episode_id(user_id, ticker, trade_date),
        text=f"{(situation_text or '')[:1500]}\n\n{transcript}"[:_QA_MAX_CHARS],
        metadata={"ticker": ticker, "trade_date": trade_date},
    )
    try:
        await store.upsert(_qa_namespace(user_id), [record])
        return True
    except Exception as exc:  # noqa: BLE001
        _logger.warning("record_agent_qa failed for %s %s: %s", ticker, trade_date, exc)
        return False


async def recall_agent_qa(
    *,
    user_id: int | None,
    situation_text: str,
    top_k: int = 2,
    store: MemoryStore | None = None,
) -> str:
    """Return prior cross-examinations of similar situations, to seed the current
    Q&A. Empty when memory is disabled or nothing relevant."""
    store = store or await get_user_memory_store(user_id)
    if store is None or not situation_text.strip():
        return ""
    hits = await store.query(_qa_namespace(user_id), situation_text, top_k=top_k)
    if not hits:
        return ""
    parts = ["### How analysts reconciled similar situations before:"]
    for h in hits:
        parts.append(f"--- {h.metadata.get('ticker', '?')} {h.metadata.get('trade_date', '?')} ---")
        parts.append(h.text)
    return "\n".join(parts)
