# Architecture integrations

This branch uses package-backed implementations as the production path. Legacy
provider, broker, standard-indicator and SQLite-checkpoint fallbacks are removed.

## LLMs: LiteLLM only

All configured LLM providers are routed in-process through
`langchain-litellm` / `ChatLiteLLM`.

The existing per-user provider keys remain the credential source. There is no
second provider-specific LangChain SDK layer and no external LiteLLM Proxy is
required. Provider routing is normalized as follows:

- OpenAI -> `openai/...`
- Anthropic -> `anthropic/...`
- Google AI Studio -> `gemini/...`
- Mistral -> `mistral/...`
- Groq -> `groq/...`
- NVIDIA NIM -> `nvidia_nim/...`
- DeepSeek -> `deepseek/...`
- Ollama -> `ollama/...`

Ollama remains server-managed through `OLLAMA_BASE_URL`; tenants cannot replace
its endpoint with a stored credential. SDK retries default to zero so the agent
runtime remains the single retry authority.

## Alpaca: official SDK only

Alpaca paper/live execution uses `alpaca-py`. The hand-written HTTP broker
implementation and package-detection fallback are removed.

## Standard technical indicators: pandas-ta-classic only

EMA, RSI, MACD, ADX, ATR and rolling volume-weighted price calculations are
provided by `pandas-ta-classic`. The application still owns product-specific
contracts such as formula sandboxing, Ichimoku output shaping, Fibonacci
display levels and custom chart-pattern algorithms.

## Checkpoints: PostgreSQL only

LangGraph checkpoints use `PostgresSaver` / `AsyncPostgresSaver`. The per-run
SQLite checkpoint fallback is removed. A PostgreSQL `DATABASE_URL` is therefore
required for analysis checkpointing.

## Vector memory: Pinecone and pgvector

Both memory backends remain supported:

- Pinecone is retained as a managed vector-memory option.
- pgvector remains the self-hosted PostgreSQL option.

Alembic owns pgvector extension/table creation; request-time memory operations
do not perform schema DDL.

## Research/reference packages

`backend.services.research_integrations` remains isolated from production
execution for OpenBB, vectorbt, empyrical/QuantStats comparisons and
PyPortfolioOpt research. Those adapters are research or validation tools, not
fallback production engines.

## Observability

OpenTelemetry remains opt-in and does not replace product WebSocket events.
When enabled, install the configured OpenTelemetry SDK/exporter/instrumentation
packages in the deployment.
