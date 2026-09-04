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

## Standard technical indicators: TA-Lib only

TA-Lib provides SMA, EMA, RSI, MACD, ADX, ATR, Bollinger Bands, the stochastic
oscillator, CCI, MFI and Williams %R. The application still owns
product-specific formula sandboxing and custom chart-pattern algorithms; unused
standalone Ichimoku/Fibonacci display helpers were removed rather than kept as
a second indicator surface.

Every wrapper in `services/indicator_service.py` returns a named Series over
the caller's index, and guards its own minimum input length so a short frame
yields NaN instead of an exception from the C library.

All of them are also exposed to the sandboxed custom-formula language as
`NAME(period)` symbols; multi-series indicators get one symbol per line
(`BBL`/`BBM`/`BBU`, `STOCHK`/`STOCHD`). The AI formula assistant's DSL prompt in
`services/formula_assist_service.py` lists the same set — it must be updated
whenever a symbol is added, or the assistant will keep hand-rolling an
approximation of an indicator that now exists.

### TA-Lib is the indicator engine

`services/indicator_service.py` calls TA-Lib directly; `pandas-ta-classic` has
been removed. TA-Lib is a C library, but the published wheels bundle it, so
neither the Docker image nor the Linux installer needs a native build step.

TA-Lib returns plain arrays rather than frames whose column names encode the
parameters that produced them, so the wrappers name their own output and the
prefix-matching helper that used to recover those columns is gone.

TA-Lib has no VWMA, and its session-anchored VWAP has a different contract from
this application's `period` semantics, so `calculate_vwap` still computes the
rolling volume-weighted typical price itself.

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

## Durable memory: Mem0 + pgvector only

Mem0 OSS is the only durable semantic-memory backend. TradingAgents provides
curated episode and Agent Q&A memories to Mem0 with `infer=False`, so there is
no second LLM extraction pass. Mem0 stores vectors in PostgreSQL/pgvector and
scopes entries with `user_id`, `agent_id`, and deterministic `run_id` values.

OpenAI and Ollama are the supported embedding providers. OpenAI uses the
user's encrypted OpenAI credential; Ollama uses the server-managed
`OLLAMA_BASE_URL`. The former custom vector-store protocol, application-owned
`memory_vectors` table, and hosted memory provider path are retired. Migration
`0030` removes their persisted schema and settings.

Mem0 owns creation and maintenance of its vector collection lazily. Alembic
continues to require the PostgreSQL pgvector extension because Mem0 depends on
it, but request-time application code does not manage a parallel custom memory
table.

## Quantitative packages

There is no `research` dependency group and no `research_integrations` adapter
module. Three packages were promoted to real dependencies and the rest were
dropped, because an optional group nothing imported was indistinguishable from
dead code.

| Package | Role |
| --- | --- |
| TA-Lib | the standard-indicator engine (see above) |
| empyrical-reloaded | risk-adjusted backtest statistics |
| PyPortfolioOpt | advisory mean-variance portfolio weights |

OpenBB, vectorbt and QuantStats were removed. OpenBB would be a second data
path beside the tool system that already owns per-user vendor credentials and
their RLS scoping. vectorbt is vectorized, so it cannot express the intrabar
stop-loss/take-profit exits `backtest_service` already implements. QuantStats
is mostly an HTML tearsheet generator, and this application has its own UI.

### empyrical-reloaded

`_compute_metrics` keeps its five money metrics in exact Decimal arithmetic.
The risk-adjusted statistics beside them — Sortino, Calmar, Omega, tail ratio,
VaR, annual return/volatility and stability — are ratios rather than money, so
empyrical computes them on floats. A ratio that comes back NaN or infinite,
which a flat equity curve produces, is reported as absent rather than
serialised as a number.

The optimizer's `calmar` objective reads empyrical's Calmar ratio. It
previously divided total return by max drawdown, which is not that ratio.

### PyPortfolioOpt

`services/portfolio_optimizer_service.py` computes mean-variance weights behind
`POST /api/trading/portfolio/optimize`, using Ledoit-Wolf shrinkage so the
covariance stays invertible on short lookbacks. It refuses fewer than two
tickers, more than thirty, and fewer than sixty overlapping trading days rather
than returning a plausible-looking weight vector built on too little data.

This is advisory only. `portfolio_rebalance_planner` remains the deterministic
authority for actionable sizing, in exact decimal arithmetic, and the optimizer
does not feed it.

### vectorbt vs NautilusTrader

Neither is used. Adopting an event-driven execution model shared between
backtest and live trading would duplicate the existing Alpaca/execution
semantics; until the project explicitly decides it wants that, both add
maintenance without removing any.

## PostgreSQL RLS

Alembic enables tenant policies on application tables carrying `user_id`; authenticated requests set transaction-local `app.user_id` / `app.is_admin`.

Production is fail-closed. The web/worker connection must be a dedicated non-owner, `NOSUPERUSER`, `NOBYPASSRLS` role. `ENVIRONMENT=production` automatically makes runtime-role validation strict.

The pgvector extension is provisioned by the database superuser before Alembic and remains required by Mem0. Durable memory collections are owned by Mem0 rather than by the application ORM/Alembic schema. Docker pins `pgvector/pgvector:0.8.6-pg16`, while the Linux installer installs or builds the same pinned extension release.

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
