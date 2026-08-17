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
formula sandboxing and custom chart-pattern algorithms; unused standalone
Ichimoku/Fibonacci display helpers were removed rather than kept as a second
indicator surface.

The `research` dependency group also contains TA-Lib so package parity checks can
be run against a second implementation without putting TA-Lib on the production
runtime path.

## Checkpoints: PostgreSQL only

LangGraph checkpoints use `PostgresSaver` / `AsyncPostgresSaver`. The per-run
SQLite checkpoint fallback is removed. A PostgreSQL `DATABASE_URL` is therefore
required for analysis checkpointing. Schema setup is single-flight per DSN and
only marked done once it has actually completed; see
`docs/architecture/backend.md` for why.

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

Alembic enables tenant policies on application tables carrying `user_id`; authenticated requests set transaction-local `app.user_id` / `app.is_admin`.

Production is fail-closed. The web/worker connection must be a dedicated non-owner, `NOSUPERUSER`, `NOBYPASSRLS` role. `ENVIRONMENT=production` automatically makes runtime-role validation strict.

The pgvector extension itself is provisioned by the database superuser before Alembic; Alembic owns the `memory_vectors` table and tenant schema changes. Docker pins `pgvector/pgvector:0.8.6-pg16`, while the Linux installer installs or builds the same pinned extension release.

Migration credentials are excluded from the application `.env`/process. Linux deployment stores them root-only in `/etc/tradingagents/migration.env`; Docker exposes the owner credential only to prepare/migrate one-shot services. Production web/worker startup never runs DDL: it verifies `alembic_version` is already at repository head and refuses to start otherwise.

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

`backend/pyproject.toml` is the hand-edited manifest and `backend/uv.lock` is the resolver-generated lock. Production installs use only:

```bash
cd backend
uv lock --check
uv sync --frozen --no-dev
```

`requirements.txt` and its export script are removed, so there is no second dependency source to drift. Research and observability remain explicit non-default dependency groups recorded in the same lock.
