# Vector memory

Pluggable long-term memory for the trading engine. Two capabilities:

1. **Episodic memory** — every completed analysis is stored once its outcome is
   known (the market *situation* embedded, with the decision, realized alpha and
   the reflection/lesson as metadata, tagged `loss`/`gain`). On later runs the
   decision nodes recall the most *similar* past situations — **losses first**, under
   a "do not repeat this mistake" header — so the engine can avoid re-taking an
   action that previously lost. This replaces the old recency-based SQL retrieval.

2. **Inter-agent Q&A** — after the analysts finish, an "Agent Q&A" graph node lets
   them cross-examine each other (a moderator picks the sharpest cross-agent
   questions; each is answered by the *target* analyst with its own LLM and
   report). The transcript feeds the research manager and is stored for recall.

## Architecture (modular)

```
core/memory/
  base.py          MemoryStore / Embedder protocols, MemoryRecord / MemoryHit
  pinecone_store.py PineconeMemoryStore (hosted or client-side embedding)
  embedders.py     OpenAIEmbedder (optional, client-side)
  factory.py       get_memory_store() — the ONLY place a backend is chosen
services/memory_service.py   record_episode / recall_episode_lessons
                             record_agent_qa / recall_agent_qa  (domain layer)
```

Callers depend only on the `MemoryStore` **protocol** and the domain functions in
`services/memory_service.py`. To use a different vector DB, implement
`MemoryStore` and return it from `factory.get_memory_store()` — nothing else
changes.

## Configuration

Memory is **disabled** (all record/recall calls become no-ops) unless
`PINECONE_API_KEY` is set — there is no fallback by design.

| Env var | Default | Meaning |
|---|---|---|
| `PINECONE_API_KEY` | _(empty → memory off)_ | Pinecone key |
| `PINECONE_INDEX` | `tradingagents-memory` | index name |
| `PINECONE_CLOUD` / `PINECONE_REGION` | `aws` / `us-east-1` | serverless location |
| `MEMORY_EMBEDDER` | `pinecone` | `pinecone` (hosted) or `openai` (client-side) |
| `PINECONE_EMBED_MODEL` | `llama-text-embed-v2` | hosted embedding model |
| `MEMORY_OPENAI_API_KEY` / `MEMORY_OPENAI_EMBED_MODEL` | _(empty)_ / `text-embedding-3-small` | only for `MEMORY_EMBEDDER=openai` |

Episodes and Q&A are namespaced per user (`ep_user_<id>` / `qa_user_<id>`), so one
user's history never leaks into another's recall.

The Q&A node is gated by the runtime flag `agent_qa_enabled` (default on).
