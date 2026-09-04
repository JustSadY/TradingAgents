"""Long-term trading memory backed by Mem0 + PostgreSQL/pgvector.

LangGraph state remains the short-lived analysis/session state. This module is
only the durable semantic-memory boundary used by performance episodes and the
optional analyst cross-examination memory.

TradingAgents already decides exactly what a durable memory contains, so Mem0
is used with ``infer=False``. That keeps memory deterministic, avoids a second
LLM extraction pass, and makes the service a thin adapter instead of maintaining
our own vector-store/embedding abstraction.

Memory is best-effort. Missing credentials, an unavailable Ollama/PostgreSQL
instance, or a Mem0 failure must never break an analysis run.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

_logger = logging.getLogger(__name__)

_SYSTEM_OWNER = "system"
_EPISODE_AGENT_ID = "trading-episodes"
_QA_AGENT_ID = "trading-agent-qa"
_SITUATION_MAX_CHARS = 4000
_QA_TRANSCRIPT_MAX_CHARS = 6000
_STORE_RESOLUTION_TTL_SECONDS = 30.0
_SEARCH_CACHE_TTL_SECONDS = 120.0
_SEARCH_CACHE_MAX_ENTRIES = 128

# Mem0 is intentionally lazy-imported so the application can still boot when
# memory is not configured. Instances are reused per effective DB/embedder
# configuration; provider secrets are represented only by a short fingerprint
# in the cache key. Parallel first-use calls share one initialization task so
# they cannot create duplicate Mem0 clients/connection pools for the same key.
_store_cache: dict[tuple[Any, ...], Any] = {}
_store_init_tasks: dict[tuple[Any, ...], asyncio.Task[Any]] = {}

# Resolving the effective store requires opening an app DB session, loading the
# user/settings rows, and decrypting a provider key. A single graph run may ask
# for memory from multiple nodes, so keep successful resolutions briefly per
# user. Explicit invalidation handles local settings/key writes; the short TTL
# bounds staleness across separate worker processes.
_user_store_cache: dict[int, tuple[float, Any]] = {}

# Short-lived semantic-search cache. Research Manager and Portfolio Manager
# commonly ask for the same episodic lessons in one run. The key stores only a
# digest of the prompt text, and writes invalidate the matching owner/agent
# scope before and after mutation so local readers never keep stale results.
_search_cache: OrderedDict[
    tuple[Any, ...],
    tuple[float, list[dict[str, Any]]],
] = OrderedDict()

_OPENAI_DIMS = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}
_OLLAMA_DIMS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "bge-m3": 1024,
    "all-minilm": 384,
}


def _owner_id(user_id: int | None) -> str:
    return str(user_id) if user_id else _SYSTEM_OWNER


def _episode_id(user_id: int | None, ticker: str, trade_date: str) -> str:
    return f"{_owner_id(user_id)}:{ticker}:{trade_date}"


def _qa_id(user_id: int | None, ticker: str, trade_date: str) -> str:
    return f"{_owner_id(user_id)}:{ticker}:{trade_date}:agent_qa"


def _secret_fingerprint(secret: str | None) -> str:
    if not secret:
        return ""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def _embedding_dimensions(provider: str, model: str) -> int:
    """Return the vector size used to create the Mem0 pgvector collection.

    Mem0's pgvector adapter needs the dimension before the first embedding is
    produced. Keep the supported UI defaults explicit and use a conservative
    provider default for custom model names.
    """
    normalized = model.split(":", 1)[0].strip().lower()
    if provider == "ollama":
        dims = _OLLAMA_DIMS.get(normalized)
        if dims is None:
            _logger.warning("Unknown Ollama memory embedding dimensions for %s; assuming 768", model)
            return 768
        return dims
    dims = _OPENAI_DIMS.get(normalized)
    if dims is None:
        _logger.warning("Unknown OpenAI memory embedding dimensions for %s; assuming 1536", model)
        return 1536
    return dims


def _mem0_connection_string(database_url: str) -> str | None:
    """Translate SQLAlchemy async PostgreSQL URLs to psycopg-compatible URLs."""
    url = (database_url or "").strip()
    replacements = (
        ("postgresql+asyncpg://", "postgresql://"),
        ("postgresql+psycopg://", "postgresql://"),
        ("postgresql+psycopg2://", "postgresql://"),
        ("postgres://", "postgresql://"),
    )
    for source, target in replacements:
        if url.startswith(source):
            return target + url[len(source) :]
    return url if url.startswith("postgresql://") else None


def _collection_name(provider: str, model: str, dimensions: int) -> str:
    # Different embedding models (even with the same dimensions) must never
    # share a vector space. The digest also keeps the SQL identifier compact.
    digest = hashlib.sha256(f"{provider}:{model}:{dimensions}".encode()).hexdigest()[:12]
    return f"tradingagents_mem0_{provider}_{digest}"


def _build_mem0(
    *,
    database_url: str,
    embedder_kind: str,
    embed_model: str,
    openai_api_key: str | None,
    ollama_base_url: str,
):
    connection_string = _mem0_connection_string(database_url)
    if not connection_string:
        raise RuntimeError("Mem0 long-term memory requires PostgreSQL")

    dimensions = _embedding_dimensions(embedder_kind, embed_model)
    collection = _collection_name(embedder_kind, embed_model, dimensions)

    # Telemetry is not needed for this internal adapter. Mem0's Python OSS
    # implementation also uses SQLite for mutation history, so keep that
    # auxiliary file in a guaranteed-writable temp directory rather than the
    # application source tree.
    os.environ.setdefault("MEM0_TELEMETRY", "false")
    mem0_dir = Path(os.environ.setdefault("MEM0_DIR", str(Path(tempfile.gettempdir()) / "tradingagents-mem0")))
    mem0_dir.mkdir(parents=True, exist_ok=True)

    from mem0 import Memory

    if embedder_kind == "ollama":
        embedder_config = {
            "provider": "ollama",
            "config": {
                "model": embed_model,
                "ollama_base_url": ollama_base_url,
                "embedding_dims": dimensions,
            },
        }
        # infer=False means this LLM is never called by TradingAgents. Mem0
        # still constructs an LLM adapter during initialization, so use the
        # same local provider and avoid introducing a cloud-key requirement.
        llm_config = {
            "provider": "ollama",
            "config": {
                "model": "llama3.2:1b",
                "ollama_base_url": ollama_base_url,
                "temperature": 0,
            },
        }
    else:
        if not openai_api_key:
            raise RuntimeError("OpenAI memory embedding requires an OpenAI API key")
        embedder_config = {
            "provider": "openai",
            "config": {
                "model": embed_model,
                "api_key": openai_api_key,
                "embedding_dims": dimensions,
            },
        }
        llm_config = {
            "provider": "openai",
            "config": {
                "model": "gpt-4.1-mini",
                "api_key": openai_api_key,
                "temperature": 0,
            },
        }

    return Memory.from_config(
        {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "connection_string": connection_string,
                    "collection_name": collection,
                    "embedding_model_dims": dimensions,
                    "hnsw": True,
                    "minconn": 1,
                    "maxconn": 5,
                },
            },
            "embedder": embedder_config,
            "llm": llm_config,
            "history_db_path": str(mem0_dir / f"{collection}-history.db"),
        }
    )


async def _get_or_build_mem0(
    cache_key: tuple[Any, ...],
    *,
    database_url: str,
    embedder_kind: str,
    embed_model: str,
    openai_api_key: str | None,
    ollama_base_url: str,
):
    """Return one shared Mem0 instance per effective configuration.

    The first caller owns a background initialization task. Other concurrent
    callers await that same task through ``shield`` so one cancelled analysis
    cannot cancel initialization needed by the rest of the process.
    """
    cached = _store_cache.get(cache_key)
    if cached is not None:
        return cached

    task = _store_init_tasks.get(cache_key)
    if task is None:

        async def _build_and_cache():
            try:
                store = await asyncio.to_thread(
                    _build_mem0,
                    database_url=database_url,
                    embedder_kind=embedder_kind,
                    embed_model=embed_model,
                    openai_api_key=openai_api_key,
                    ollama_base_url=ollama_base_url,
                )
                _store_cache[cache_key] = store
                return store
            finally:
                _store_init_tasks.pop(cache_key, None)

        task = asyncio.create_task(_build_and_cache())
        _store_init_tasks[cache_key] = task

    return await asyncio.shield(task)


def invalidate_user_memory_store_cache(user_id: int | None = None) -> None:
    """Drop local Mem0 resolution/search state after settings or key changes."""
    if user_id is None:
        _user_store_cache.clear()
        _search_cache.clear()
        return

    _user_store_cache.pop(int(user_id), None)
    owner = _owner_id(user_id)
    for key in tuple(_search_cache):
        if len(key) > 1 and key[1] == owner:
            _search_cache.pop(key, None)


async def get_user_memory_store(user_id: int | None):
    """Resolve the user's Mem0 instance from current settings and encrypted keys.

    Mem0 OSS on the application's PostgreSQL/pgvector database is the only
    durable memory backend. Per-user settings select either OpenAI or Ollama for
    embeddings; no legacy store selection or hosted-memory credential path is
    consulted at runtime.
    """
    if not user_id:
        return None

    user_id = int(user_id)
    cached = _user_store_cache.get(user_id)
    now = monotonic()
    if cached is not None:
        expires_at, store = cached
        if now <= expires_at:
            return store
        _user_store_cache.pop(user_id, None)

    try:
        from backend.core.config import get_settings
        from backend.core.database import AsyncSessionLocal
        from backend.core.rls_context import set_user_background_context
        from backend.repositories.settings import get_app_settings
        from backend.repositories.users import get_user_by_id
        from backend.services.user_service import get_user_api_key

        app_config = get_settings()
        connection_string = _mem0_connection_string(app_config.DATABASE_URL)
        if not connection_string:
            _logger.warning("Mem0 memory is disabled because DATABASE_URL is not PostgreSQL")
            return None

        fernet = app_config.get_fernet()
        async with AsyncSessionLocal() as db:
            user = await get_user_by_id(db, user_id)
            if not user:
                return None
            await set_user_background_context(db, user_id)
            row = await get_app_settings(db, user_id)

            requested_embedder = (getattr(row, "memory_embedder", None) or "openai").strip().lower()
            embedder_kind = "ollama" if requested_embedder == "ollama" else "openai"
            openai_embed_model = getattr(row, "memory_openai_embed_model", None) or "text-embedding-3-small"
            ollama_embed_model = getattr(row, "memory_ollama_embed_model", None) or "nomic-embed-text"
            embed_model = ollama_embed_model if embedder_kind == "ollama" else openai_embed_model
            openai_key = None
            if embedder_kind == "openai":
                openai_key = get_user_api_key(user, "openai", fernet)
                if not openai_key:
                    return None

        ollama_base_url = app_config.OLLAMA_BASE_URL.rstrip("/")
        dimensions = _embedding_dimensions(embedder_kind, embed_model)
        cache_key = (
            connection_string,
            embedder_kind,
            embed_model,
            dimensions,
            ollama_base_url if embedder_kind == "ollama" else "",
            _secret_fingerprint(openai_key),
        )
        store = await _get_or_build_mem0(
            cache_key,
            database_url=app_config.DATABASE_URL,
            embedder_kind=embedder_kind,
            embed_model=embed_model,
            openai_api_key=openai_key,
            ollama_base_url=ollama_base_url,
        )
        _user_store_cache[user_id] = (monotonic() + _STORE_RESOLUTION_TTL_SECONDS, store)
        return store
    except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
        _logger.warning("Could not resolve Mem0 memory for user_id=%s: %s", user_id, exc)
        return None


def _search_cache_key(store, *, owner: str, agent_id: str, query: str, top_k: int) -> tuple[Any, ...]:
    query_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return id(store), owner, agent_id, query_digest, int(top_k)


def _invalidate_search_cache(store, *, owner: str, agent_id: str) -> None:
    scope = (id(store), owner, agent_id)
    for key in tuple(_search_cache):
        if key[:3] == scope:
            _search_cache.pop(key, None)


async def _replace_memory(
    store,
    *,
    owner: str,
    agent_id: str,
    run_id: str,
    text: str,
    metadata: dict[str, Any],
) -> None:
    """Idempotently replace one logical TradingAgents memory in Mem0."""
    _invalidate_search_cache(store, owner=owner, agent_id=agent_id)
    try:
        await asyncio.to_thread(store.delete_all, user_id=owner, agent_id=agent_id, run_id=run_id)
    except Exception as exc:  # duplicate avoidance is best-effort; writing is more important
        _logger.debug("Mem0 pre-write delete failed for run_id=%s: %s", run_id, exc)

    await asyncio.to_thread(
        store.add,
        text,
        user_id=owner,
        agent_id=agent_id,
        run_id=run_id,
        metadata=metadata,
        infer=False,
    )
    # A search may have raced between delete and add; clear it again after the
    # successful write so subsequent recalls observe the new memory.
    _invalidate_search_cache(store, owner=owner, agent_id=agent_id)


def _normalize_hits(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("memories") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _hit_metadata(hit: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(hit.get("metadata") or {})
    # Mem0/vector-store versions have differed on whether custom payload fields
    # are nested under metadata or returned at the top level. Merge only known
    # TradingAgents fields so the formatter remains version-tolerant.
    for key in (
        "ticker",
        "trade_date",
        "signal",
        "decision",
        "reflection",
        "raw_return",
        "alpha_return",
        "outcome",
        "observed_at",
        "outcome_available_at",
        "transcript",
        "memory_type",
        "memory_key",
    ):
        if key in hit and key not in metadata:
            metadata[key] = hit[key]
    return metadata


def _hit_score(hit: dict[str, Any]) -> float:
    try:
        return float(hit.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def _search_memories(store, *, owner: str, agent_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
    cache_key = _search_cache_key(store, owner=owner, agent_id=agent_id, query=query, top_k=top_k)
    now = monotonic()
    cached = _search_cache.get(cache_key)
    if cached is not None:
        created_at, hits = cached
        if now - created_at <= _SEARCH_CACHE_TTL_SECONDS:
            _search_cache.move_to_end(cache_key)
            return [dict(hit) for hit in hits]
        _search_cache.pop(cache_key, None)

    payload = await asyncio.to_thread(
        store.search,
        query,
        filters={"user_id": owner, "agent_id": agent_id},
        top_k=top_k,
    )
    hits = _normalize_hits(payload)
    _search_cache[cache_key] = (now, hits)
    _search_cache.move_to_end(cache_key)
    while len(_search_cache) > _SEARCH_CACHE_MAX_ENTRIES:
        _search_cache.popitem(last=False)
    return [dict(hit) for hit in hits]


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
    store=None,
) -> bool:
    """Store one completed, outcome-known analysis as a curated Mem0 memory."""
    store = store or await get_user_memory_store(user_id)
    if store is None:
        return False

    outcome = "loss" if (alpha_return is not None and alpha_return < 0) else "gain"
    text = (situation_text or decision or "")[:_SITUATION_MAX_CHARS]
    if reflection:
        text = f"{text}\n\nLesson: {reflection}"
    now = datetime.now(UTC).isoformat()
    memory_key = _episode_id(user_id, ticker, trade_date)
    metadata = {
        "memory_key": memory_key,
        "memory_type": "trading_episode",
        "ticker": ticker,
        "trade_date": trade_date,
        "signal": signal or "",
        "decision": (decision or "")[:1500],
        "reflection": reflection or "",
        "raw_return": float(raw_return) if raw_return is not None else 0.0,
        "alpha_return": float(alpha_return) if alpha_return is not None else 0.0,
        "outcome": outcome,
        "observed_at": now,
        "outcome_available_at": now,
    }
    try:
        await _replace_memory(
            store,
            owner=_owner_id(user_id),
            agent_id=_EPISODE_AGENT_ID,
            run_id=memory_key,
            text=text,
            metadata=metadata,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
        _logger.warning("record_episode failed for %s %s: %s", ticker, trade_date, exc)
        return False


async def record_agent_qa(
    *,
    user_id: int | None,
    ticker: str,
    trade_date: str,
    situation_text: str,
    transcript: str,
    store=None,
) -> bool:
    """Store one cross-examination transcript in a separate Mem0 agent scope."""
    if not transcript.strip():
        return False
    store = store or await get_user_memory_store(user_id)
    if store is None:
        return False

    observed_at = datetime.now(UTC).isoformat()
    situation = (situation_text or f"Cross-examination for {ticker}")[:_SITUATION_MAX_CHARS]
    transcript = transcript[:_QA_TRANSCRIPT_MAX_CHARS]
    memory_key = _qa_id(user_id, ticker, trade_date)
    metadata = {
        "memory_key": memory_key,
        "memory_type": "agent_qa",
        "ticker": ticker,
        "trade_date": trade_date,
        "transcript": transcript,
        "observed_at": observed_at,
    }
    try:
        await _replace_memory(
            store,
            owner=_owner_id(user_id),
            agent_id=_QA_AGENT_ID,
            run_id=memory_key,
            text=f"{situation}\n\n{transcript}",
            metadata=metadata,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
        _logger.warning("record_agent_qa failed for %s %s: %s", ticker, trade_date, exc)
        return False


async def recall_agent_qa(
    *,
    user_id: int | None,
    situation_text: str,
    top_k: int = 3,
    as_of: str | None = None,
    store=None,
) -> str:
    """Recall similar prior cross-examinations without leaking future transcripts."""
    store = store or await get_user_memory_store(user_id)
    if store is None or not situation_text.strip():
        return ""

    query_limit = max(top_k, top_k * 5 if as_of else top_k)
    try:
        hits = await _search_memories(
            store,
            owner=_owner_id(user_id),
            agent_id=_QA_AGENT_ID,
            query=situation_text,
            top_k=query_limit,
        )
    except Exception as exc:  # noqa: BLE001 — Q&A memory is advisory
        _logger.warning("recall_agent_qa failed: %s", exc)
        return ""

    if as_of:
        from backend.core.temporal import parse_iso_date

        cutoff = parse_iso_date(as_of, field_name="as_of")
        safe_hits = []
        for hit in hits:
            observed = _hit_metadata(hit).get("observed_at")
            if not observed:
                continue
            try:
                observed_date = datetime.fromisoformat(str(observed).replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if observed_date <= cutoff:
                safe_hits.append(hit)
        hits = safe_hits[:top_k]
    else:
        hits = hits[:top_k]

    if not hits:
        return ""

    parts = ["### Memory: similar prior analyst cross-examinations"]
    for hit in hits:
        metadata = _hit_metadata(hit)
        transcript = str(metadata.get("transcript") or "").strip()
        if not transcript:
            continue
        ticker = metadata.get("ticker", "?")
        trade_date = metadata.get("trade_date", "?")
        parts.append(
            f"\n**{ticker} · {trade_date} · similarity {_hit_score(hit):.2f}**\n"
            f"{transcript[:_QA_TRANSCRIPT_MAX_CHARS]}"
        )
    return "\n".join(parts) if len(parts) > 1 else ""


async def recall_episode_lessons(
    *,
    user_id: int | None,
    situation_text: str,
    top_k: int = 5,
    as_of: str | None = None,
    store=None,
) -> str:
    """Return similar outcome-known episodes, with losses shown first."""
    store = store or await get_user_memory_store(user_id)
    if store is None or not situation_text.strip():
        return ""

    query_limit = max(top_k, top_k * 5 if as_of else top_k)
    try:
        hits = await _search_memories(
            store,
            owner=_owner_id(user_id),
            agent_id=_EPISODE_AGENT_ID,
            query=situation_text,
            top_k=query_limit,
        )
    except Exception as exc:  # noqa: BLE001 — memory is advisory
        _logger.warning("recall_episode_lessons failed: %s", exc)
        return ""

    if as_of:
        from backend.core.temporal import parse_iso_date

        cutoff = parse_iso_date(as_of, field_name="as_of")
        safe_hits = []
        for hit in hits:
            available = _hit_metadata(hit).get("outcome_available_at")
            if not available:
                # Outcome memories without a trustworthy availability timestamp
                # are never eligible for historical replay.
                continue
            try:
                available_date = datetime.fromisoformat(str(available).replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if available_date <= cutoff:
                safe_hits.append(hit)
        hits = safe_hits[:top_k]
    else:
        hits = hits[:top_k]
    if not hits:
        return ""

    losses = [hit for hit in hits if _hit_metadata(hit).get("outcome") == "loss"]
    gains = [hit for hit in hits if _hit_metadata(hit).get("outcome") != "loss"]
    parts: list[str] = ["### Memory: similar past situations"]

    if losses:
        parts.append("\n**Actions that previously led to a loss — do NOT repeat the same mistake:**")
        parts.extend(_format_hit(hit) for hit in losses)
    if gains:
        parts.append("\n**Actions that previously worked out:**")
        parts.extend(_format_hit(hit) for hit in gains)

    return "\n".join(parts)


def _format_hit(hit: dict[str, Any]) -> str:
    metadata = _hit_metadata(hit)
    try:
        alpha = float(metadata.get("alpha_return", 0.0) or 0.0)
    except (TypeError, ValueError):
        alpha = 0.0
    header = (
        f"- {metadata.get('ticker', '?')} on {metadata.get('trade_date', '?')} "
        f"({metadata.get('signal') or 'N/A'}, alpha {alpha:+.1%}, similarity {_hit_score(hit):.2f})"
    )
    reflection = metadata.get("reflection")
    return f"{header}\n  {reflection}" if reflection else header
