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
its endpoint with a stored credential. SDK retries default to zero.

Structured-output calls no longer implement a second retry loop. They delegate
to `agents.runtime.resilience.retry_call`, which owns retry classification,
backoff and per-call timeout. Semantic structured-output fallback/self-correction
is still allowed, but it does not create another transport retry authority.

## Alpaca: official SDK only

Alpaca paper/live execution uses `alpaca-py`. The hand-written HTTP broker
implementation and package-detection fallback are removed.

## Standard technical indicators: pandas-ta-classic only

EMA, RSI, MACD, ADX, ATR and rolling volume-weighted price calculations are
provided by `pandas-ta-classic`. The application still owns product-specific
contracts such as formula sandboxing, Ichimoku output shaping, Fibonacci
display levels and custom chart-pattern algorithms.

The `research` dependency group also contains TA-Lib so package parity checks can
be run against a second implementation without putting TA-Lib on the production
runtime path.

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

Research and validation dependencies are isolated from the production runtime:

```bash
cd backend
uv sync --group research
```

The group contains OpenBB, TA-Lib, vectorbt, empyrical-reloaded, QuantStats and
PyPortfolioOpt. `backend.services.research_integrations` is the stable adapter
surface for those packages.

OpenBB is a research-data pilot, not a silent production data fallback.
QuantStats/empyrical are cross-validation oracles. PyPortfolioOpt remains a
research optimizer while actionable portfolio sizing stays deterministic in the
application.

### vectorbt vs NautilusTrader

`vectorbt` is the current research/reference backtester because this project
needs fast vectorized strategy validation without replacing its execution
engine. NautilusTrader is not added now: adopting it would make sense only if
the project explicitly decides that backtest and live execution must share one
event-driven execution model. Until that requirement exists, adding Nautilus
would duplicate Alpaca/execution semantics and increase maintenance.

## PostgreSQL RLS

Alembic enables tenant RLS policies on application tables carrying `user_id`.
The application sets transaction-local `app.user_id` / `app.is_admin` values
after authentication.

PostgreSQL owners, superusers and roles with `BYPASSRLS` can bypass ordinary RLS.
Startup now validates the connected runtime role. Existing deployments get a
warning if the role can bypass RLS; production deployments can make this
fail-closed with:

```bash
RLS_STRICT_MODE=true
```

Strict mode requires a dedicated non-owner, `NOBYPASSRLS` runtime database role.
Keep schema migration ownership separate from the application runtime role.

## Observability

Infrastructure OTLP tracing remains opt-in and does not replace product
WebSocket events. Install the observability group when using it:

```bash
cd backend
uv sync --group observability
```

For standard OpenTelemetry export:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=tradingagents-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

For Langfuse LLM/agent tracing:

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=...
```

The LiteLLM LangChain client automatically receives the Langfuse callback when
`LANGFUSE_ENABLED=true`. Do not enable `OTEL_ENABLED` and the in-process Langfuse
callback together; use an OpenTelemetry Collector to fan out traces if both
destinations are required.

## Dependency locking

`pyproject.toml` remains the hand-edited dependency manifest. The `research` and
`observability` dependency groups are deliberately non-default.

A correct `uv.lock` must be generated by the uv resolver and committed before
claiming frozen/reproducible installs. Do not hand-edit or fabricate the lock.
Regenerate it in a networked development environment with:

```bash
cd backend
uv lock
uv lock --check
```

After the lock is present and current, deployment/export scripts can be switched
back to `uv sync --frozen` / `uv export --locked`.
