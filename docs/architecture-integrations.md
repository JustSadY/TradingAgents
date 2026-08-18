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

`pandas-ta-classic` provides SMA, EMA, RSI, MACD, ADX, ATR, Bollinger Bands,
the stochastic oscillator, CCI, MFI, Williams %R, OBV and rolling
volume-weighted price. The application still owns product-specific formula
sandboxing and custom chart-pattern algorithms; unused standalone
Ichimoku/Fibonacci display helpers were removed rather than kept as a second
indicator surface.

Every wrapper in `services/indicator_service.py` passes `talib=False` and reads
its result columns by prefix, because pandas-ta embeds parameters in column
names (`BBU_20_2.0`, `STOCHk_14_3_3`, `CCI_20_0.015`) and the constant in that
suffix is not always the one that was passed in.

All of them except OBV are also exposed to the sandboxed custom-formula
language as `NAME(period)` symbols; multi-series indicators get one symbol per
line (`BBL`/`BBM`/`BBU`, `STOCHK`/`STOCHD`). OBV is cumulative and takes no
period, so it has no formula symbol. The AI formula assistant's DSL prompt in
`services/formula_assist_service.py` lists the same set — it must be updated
whenever a symbol is added, or the assistant will keep hand-rolling an
approximation of an indicator that now exists.

### Why not TA-Lib

TA-Lib stays in the `research` dependency group as a parity oracle rather than
the production engine. It is a C library, so promoting it would add a native
build step to the Docker image and the Linux installer, and it would buy no
additional coverage: `pandas-ta-classic` already implements every standard
indicator this project exposes. Parity checks against TA-Lib run through
`backend.services.research_integrations.talib_standard_indicators`.

## Conditional volatility: arch

`arch` is a production dependency, not a research one. `services/volatility_service.py`
fits GARCH, TARCH/GJR or EGARCH to a return series and forecasts over a
horizon, deriving parametric VaR and expected shortfall from the forecast.
`quant_tools` still reports trailing realized volatility; this is the forward
view, and the two are deliberately separate numbers.

The `volatility_forecast` agent tool exposes it to the quant analyst, the risk
debate and the portfolio manager. It is `point_in_time`: the fit only uses
history up to the requested date, so replaying an earlier date reproduces the
same forecast.

Two constraints worth knowing before changing it:

- **arch must stay on 8.x.** 7.2 calls pandas' `deprecate_kwarg` with a
  signature pandas 3 no longer accepts, so it raises at import.
- **EGARCH cannot be forecast analytically past one step.** It models
  log-variance, so multi-step variance has no closed form and arch refuses.
  Those forecasts simulate the variance path instead, with a fixed seed so the
  same request does not return a different number each call.

## Strategy parameter search: Optuna

`services/optimization_service.py` searches rule-based strategy parameters
using the same `run_backtest_simulation` the Backtest page runs, so an
optimized parameter set is reproducible by re-running that backtest with it.

Two rules keep this honest:

- **The simulation owns the parameter space.** Bounds live in
  `backtest_service.STRATEGY_PARAM_SPACE` and every proposal passes through
  `normalise_strategy_params`, so a sampler cannot produce a combination the
  backtest would reject — an inverted MACD pair or crossed RSI bands are
  repaired, not run.
- **Optuna never runs the objective itself.** `study.optimize` wants a
  synchronous callable and the backtest is async, so trials are driven from the
  event loop through the ask/tell API rather than pushing an event loop into a
  worker thread.

A trial whose backtest failed, or which traded fewer than three times, scores
`None` and cannot win — otherwise "never traded" wins on drawdown and win rate.
Each search also measures the shipped defaults, so the result reports an
improvement over them rather than a bare number. Runs are persisted to
`optimization_runs` because a search is tens of backtests and its value is the
parameter set at the end.

`consensus` is not optimizable: it replays stored analyses and has nothing to
tune.

## Checkpoints: PostgreSQL only

LangGraph checkpoints use `PostgresSaver` / `AsyncPostgresSaver`. The per-run
SQLite checkpoint fallback is removed. A PostgreSQL `DATABASE_URL` is therefore
required for analysis checkpointing. Schema setup is single-flight per DSN and
only marked done once it has actually completed; see
`docs/architecture/backend.md` for why.

### Who creates the checkpoint tables

LangGraph creates them through `setup()`, which needs CREATE on the schema. In
a hardened deployment the application connects with a non-owner, NOBYPASSRLS
role that deliberately has no such privilege, so **the app cannot bootstrap
them itself** — `setup()` fails with `permission denied for schema public`.

They are provisioned with the migration credential instead:

```bash
MIGRATION_DATABASE_URL=... python backend/scripts/provision-checkpoints.py
```

`deploy/install.sh` and `deploy/update.sh` run this immediately after
`alembic upgrade head`. Run it again after a LangGraph upgrade that adds a
checkpoint migration. The tables end up owned by the migrator, so the runtime
role picks up DML through the default privileges
`deploy/provision-postgres-roles.sh` grants it.

At runtime a privilege failure from `setup()` is therefore not fatal on its
own: the checkpointer probes whether the tables exist, continues if they do,
and otherwise raises an error naming the provisioning command. Every other
`setup()` failure still propagates.

## Vector memory: Pinecone and pgvector

Both memory backends remain supported:

- Pinecone is retained as a managed vector-memory option.
- pgvector remains the self-hosted PostgreSQL option.

Alembic owns the pgvector *tables*, but not the extension: revision
`20260814_0018` raises `pgvector extension is not installed` rather than
creating it, because `CREATE EXTENSION` needs a privilege the migration role
is not guaranteed to have. Request-time memory operations perform no schema DDL.

The extension is provisioned before migrations run:

- `deploy/provision-postgres-roles.sh` runs `CREATE EXTENSION IF NOT EXISTS
  vector` for a locally managed database.
- `backend/scripts/provision-pgvector.py` is the preflight `deploy/install.sh`
  and `deploy/update.sh` run in every topology, including `SKIP_DB=1`, which
  skips the role-provisioning script entirely. It creates the extension when
  the migration credential may, and otherwise stops with the SQL an operator
  has to run themselves.

It also fails when the extension is installed but the `vector` type does not
resolve — a managed provider such as Supabase installs extensions into an
`extensions` schema, which leaves `type "vector" does not exist` two statements
into the migration unless that schema is on the search_path of both the
migration and runtime roles.

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
