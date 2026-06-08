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

## Configuration (per user)

Everything is **per user** and set from the app's **Settings → Memory** tab —
there are no server-level memory env vars. Memory is **disabled** (all
record/recall calls become no-ops) for a user until they add a Pinecone API key.

| Setting | Where | Default |
|---|---|---|
| Pinecone API key | encrypted per-user API key, provider `pinecone` | _(none → memory off)_ |
| `pinecone_index` | AppSettings | `tradingagents-memory` |
| `pinecone_cloud` / `pinecone_region` | AppSettings | `aws` / `us-east-1` |
| `memory_embedder` | AppSettings | `pinecone` (hosted) or `openai` (client-side) |
| `pinecone_embed_model` | AppSettings | `llama-text-embed-v2` |
| `memory_openai_embed_model` | AppSettings | `text-embedding-3-small` (uses the user's `openai` key) |
| `agent_qa_enabled` | AppSettings | on |

`services.memory_service.get_user_memory_store(user_id)` resolves and caches a
store from that user's settings + keys. Episodes and Q&A are namespaced per user
(`ep_user_<id>` / `qa_user_<id>`), so one user's history never leaks into
another's recall.
